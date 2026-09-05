"""The proof workspace service. Assembles, refuses, and records two fields.

What it owns
------------
Nothing durable. There is no table here, no file root and no migration: a
bundle is built from rows other services already own, a share approval lives
in process memory with a TTL, and the two evidence fields this package can
fill are written through :meth:`TaskService.record_evidence`, which is the
only function in this product that writes them.

What it is forbidden to build (ADR-0004 2, ADR-0009 5)
-------------------------------------------------------
* **No outbound client.** ``OUTBOUND_CLIENT_MODULES`` stays at five. External
  sharing goes out through the existing ``compose`` chain and its write
  client; this package hands a file to the browser and nothing else
  (ADR-0009 11).
* **No second vault or signer.** Nothing here touches key material.
* **No second gate.** The verdicts in a bundle were decided by
  :mod:`station_api.tasks.gate` and :mod:`station_api.modules.completion`;
  this service copies them.
* **No task-state write.** A bundle changes no state, and neither does an
  acceptance. ``TaskService.transition`` is still the only function that
  writes ``task_record.state`` - and this package deliberately never calls
  it (see :meth:`record_acceptance`).

Two fields, and why acceptance does not move anything
------------------------------------------------------
``user_acceptance`` is a person's act, and ADR-0009 8 is precise about which
direction it flows: acceptance is the **input** to a publication decision, not
its output. Making the acceptance route also transition the task would give
``ready_to_publish`` a producer that is not "three separately verified pieces
of evidence", which is the property SI-222 exists to protect. So this method
records the field and stops; the state stays where it was, and the gate
recomputes on its own.

``public_share`` is the fourth field, opened by ADR-0009 1 and fillable only
from an archived send. This service reads that send's own outcome to decide
``verified`` rather than trusting the caller: a send that came back
``outcome_unknown`` produces a reference that exists and is *not* verified,
which is exactly what the four-level model says about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from station_api.agent.errors import AgentError
from station_api.agent.service import AgentService, RunView
from station_api.downloads import safe_download_filename, split_suffix
from station_api.evidence.service import EvidenceError, EvidenceService
from station_api.modules.fields import EvidenceField
from station_api.proof.approvals import SHARE_TOKEN_TTL_SECONDS, ShareApproval
from station_api.proof.artifacts import (
    BODY_EMBEDDED,
    CONTENT_ENCODING,
    read_workspace_bodies,
)
from station_api.proof.bundle import (
    BUNDLE_MEDIA_TYPE,
    BUNDLE_SUFFIX,
    BundleFormat,
    BundleFormatError,
    ProofBundle,
    build_bundle,
    render,
    safe_text,
)
from station_api.proof.language import assert_no_forbidden_claim
from station_api.security.tokens import SingleUseStore
from station_api.tasks.service import TaskError, TaskService, TaskView

#: The write outcome that makes an archived send a *verified* public share.
#:
#: One value out of five. ``in_flight``, ``refused``, ``outcome_unknown`` and
#: ``not_sent`` all describe a record that exists without establishing that
#: anything was published, and reporting those as verified would be the
#: "presence of a row is success" mistake the whole evidence model refuses.
ACCEPTED_WRITE_OUTCOME = "accepted"

#: What a single artifact is delivered as, whatever its name says.
#:
#: One value, never derived from the file's extension. A workspace may hold a
#: ``.html`` file - the write tool takes any allow-listed name - and Station is
#: a same-origin product with no CORS middleware, so serving one as
#: ``text/html`` would put attacker-authored markup on the application's own
#: origin. Every artifact is UTF-8 text by construction, so ``text/plain`` is
#: also simply true; the global ``nosniff`` header and the ``attachment``
#: disposition close the two ways a browser could decide otherwise.
ARTIFACT_MEDIA_TYPE = f"text/plain; charset={CONTENT_ENCODING}"


class ProofError(Exception):
    """A proof operation was refused. The message is safe to show a user."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class DeliveredBundle:
    """A built bundle on its way to the browser. Never on its way to a path."""

    payload: bytes
    media_type: str
    suffix: str
    sha256: str
    bundle_format: str
    #: When the copy was made. Beside the bytes, never inside them, so two
    #: deliveries of an unchanged bundle are byte-identical.
    delivered_at: datetime


@dataclass(frozen=True, slots=True)
class DeliveredArtifact:
    """One artifact on its way to the browser, as the file rather than about it.

    ``sha256`` is the file's own digest and ``bundle_sha256`` is the digest of
    the bundle the approval was minted against. Both travel, because they
    answer two different questions: the first is what the reader checks their
    saved copy against, the second is which reviewed document this delivery
    belonged to.
    """

    payload: bytes
    media_type: str
    filename: str
    name: str
    sha256: str
    bundle_sha256: str
    delivered_at: datetime


class ProofService:
    """Builds bundles, spends approvals, records two fields. One per process."""

    def __init__(
        self,
        *,
        tasks: TaskService,
        agent: AgentService,
        data_dir: Path,
        evidence: EvidenceService | None = None,
        approvals: SingleUseStore[ShareApproval] | None = None,
    ) -> None:
        self._tasks = tasks
        self._agent = agent
        # Required and without a default, deliberately. A proof service that
        # could be built without a workspace root would build bundles that
        # silently carry no artifact bodies - which is precisely the defect
        # this package was measured to have, reintroduced as a wiring mistake
        # nobody would see. The reading itself still goes through the agent
        # package's own defences; what is passed here is only the root they are
        # applied under.
        self._data_dir = data_dir
        self._evidence = evidence
        self._approvals: SingleUseStore[ShareApproval] = (
            approvals
            if approvals is not None
            else SingleUseStore[ShareApproval](ttl_seconds=SHARE_TOKEN_TTL_SECONDS)
        )

    @property
    def approval_ttl_seconds(self) -> int:
        return self._approvals.ttl_seconds

    @property
    def pending_approvals(self) -> int:
        return self._approvals.pending_count

    @property
    def approval_capacity(self) -> int:
        """How many unspent approvals this store keeps at once.

        Exposed so a test can read it off the *shipped* service rather than
        off a store it built itself. The default store used to be unbounded,
        and an unbounded store looks identical from the outside until
        somebody counts.
        """
        return self._approvals.capacity

    # --- reads -------------------------------------------------------------

    def build(self, task_id: str) -> ProofBundle:
        """Assemble the bundle for one task. Changes nothing.

        Every input is read through the service that owns it, so this cannot
        report a fact the rest of the product would disagree with. It is a
        pure read: no row is written, no file is created and no request leaves
        this process.

        Both owners' refusals are translated, and the second half of that is
        newer than the first. ``AgentService.workspace_files`` walks the
        workspace for reparse points and raises :class:`WorkspaceError` when
        it finds one - a junction planted in ``workspace/v1/<task_id>`` is the
        real case, and ``mklink /J`` needs no administrator right. That
        exception used to travel straight out of every proof route, which
        catches ``(ProofError, TaskError)`` only, and became an unhandled 500.
        The generic contract redacts the body, so nothing leaked; what the
        person lost was the *stated* refusal. The workspace layer knew exactly
        what was wrong and said so, and the route replaced that sentence with
        "an error occurred".

        ``AgentError`` rather than ``WorkspaceError`` alone, because it is the
        base every refusal in that package carries a ``reason`` on, and a
        proof read that grows a second agent-side failure should not have to
        remember to add it here.
        """
        try:
            view = self._tasks.get(task_id)
            gate = self._tasks.gate(task_id)
            completion = self._tasks.module_completion(task_id)
        except TaskError as exc:
            raise ProofError(str(exc), reason=exc.reason) from exc

        try:
            runs: tuple[RunView, ...] = self._agent.list_runs(task_id)
            files = self._agent.workspace_files(task_id)
            # Read through ``agent.workspace`` rather than around it: the
            # reparse-point walk, the containment check and the per-file
            # ceiling are the same ones the runner writes under. A
            # ``WorkspaceError`` this package does not know how to report per
            # file - a junction planted on the directory, say - travels out
            # here as an ``AgentError`` and becomes the stated refusal the
            # route already knows how to answer with, exactly as the listing
            # above does.
            artifacts = read_workspace_bodies(self._data_dir, task_id, files)
        except AgentError as exc:
            raise ProofError(str(exc), reason=exc.reason) from exc

        return build_bundle(
            task=view,
            gate=gate,
            completion=completion,
            runs=runs,
            artifacts=artifacts,
        )

    # --- the single-use share approval -------------------------------------

    def prepare_share(
        self, task_id: str, *, session_id: str
    ) -> tuple[str, ProofBundle]:
        """Build the bundle and mint one approval bound to its digest.

        Two requests rather than one, the shape the composer uses for signing
        and sending (ADR-0002 2): a person sees *what would leave* and then,
        separately, asks for it. The token is single-use and short-lived, and
        it carries the digest of the exact document that was shown - so a
        bundle that changed between the two requests cannot be delivered
        against an approval given for the old one.
        """
        bundle = self.build(task_id)
        token = self._approvals.issue(
            ShareApproval(
                task_id=bundle.task_id,
                session_id=session_id,
                bundle_sha256=bundle.sha256,
                source_version_id=bundle.source_version_id,
            )
        )
        return token, bundle

    def deliver_share(
        self,
        task_id: str,
        *,
        session_id: str,
        share_token: str,
        bundle_format: BundleFormat,
    ) -> DeliveredBundle:
        """Spend one approval and hand the bundle to the browser, once.

        The approval is consumed **before** anything else is checked, and it
        is consumed on every outcome - :class:`SingleUseStore` removes the
        entry under its own lock - so a refusal here does not leave a token
        that can be tried again. The bundle is then rebuilt and its digest
        compared: this is the point at which "if the artifact changes the old
        approval falls" stops being a sentence and becomes a comparison
        (ADR-0009 4).
        """
        bundle = self._spend(task_id, session_id=session_id, share_token=share_token)

        try:
            payload = render(bundle.document, bundle_format=bundle_format)
        except BundleFormatError as exc:
            raise ProofError(str(exc), reason="format_unknown") from exc

        return DeliveredBundle(
            payload=payload,
            media_type=BUNDLE_MEDIA_TYPE[bundle_format],
            suffix=BUNDLE_SUFFIX[bundle_format],
            sha256=bundle.sha256,
            bundle_format=bundle_format,
            delivered_at=datetime.now(UTC),
        )

    def _spend(
        self, task_id: str, *, session_id: str, share_token: str
    ) -> ProofBundle:
        """Consume one approval and hand back the bundle it was given for.

        Every check the two delivery paths share, in one place, because they
        are not allowed to differ: an artifact leaving this machine and a
        bundle leaving this machine are the same event with different bytes.
        The approval is consumed **before** anything else is checked and on
        every outcome - :class:`SingleUseStore` removes the entry under its own
        lock - so a refusal here does not leave a token that can be tried
        again.
        """
        accepted, approval = self._approvals.consume(share_token)
        if not accepted or approval is None:
            raise ProofError(
                "Bu paylasim onayi gecersiz, suresi dolmus veya zaten "
                "kullanilmis. Paketi yeniden hazirlayin.",
                reason="approval_invalid",
            )
        if approval.session_id != session_id:
            raise ProofError(
                "Bu onay baska bir oturuma ait.", reason="approval_foreign_session"
            )
        if approval.task_id != task_id:
            raise ProofError(
                "Bu onay baska bir goreve ait.", reason="approval_foreign_task"
            )

        bundle = self.build(task_id)
        if bundle.sha256 != approval.bundle_sha256:
            raise ProofError(
                "Paket onaydan bu yana degisti; ozet artik eslesmiyor. Yeni "
                "paketi okuyup yeni bir onay verin.",
                reason="bundle_changed",
            )
        if bundle.source_version_id != approval.source_version_id:
            # Belt and braces: the content version is inside the document, so
            # a change to it already changes the digest above. It is compared
            # separately because the two facts are separable - a document
            # could be restructured without the task's content moving - and a
            # binding that only holds transitively is a binding nobody
            # noticed breaking (ADR-0004 5).
            raise ProofError(
                "Gorevin icerik surumu onaydan bu yana degisti.",
                reason="content_version_changed",
            )
        return bundle

    def deliver_artifact(
        self, task_id: str, *, session_id: str, share_token: str, name: str
    ) -> DeliveredArtifact:
        """Hand one artifact to the browser as the file itself.

        The surface a person actually wanted. The bundle is the reviewable
        document *about* a task; this is the report, the note or the JSON the
        run produced, delivered under its own name with its own digest.

        It shares :meth:`_spend` with the bundle download and therefore shares
        every refusal: one single-use approval, bound to the session, the task,
        the content version and the bundle digest. That last binding is what
        makes this route safe to exist at all - since the bodies are inside the
        document, ``bundle_sha256`` now covers the artifact's bytes, so an
        approval a person gave after reading a bundle authorises exactly the
        bytes they read and nothing that has changed since.

        The body is taken **out of the built document** rather than read again
        from disk. A second read would be a second answer: the file could
        change between the digest comparison above and the delivery, and what
        would leave would be bytes no approval had ever covered.

        No path is opened here and no name from the request reaches the
        filesystem. ``name`` selects an entry from a document that was built
        from the workspace listing; a name that is not in that list is a
        refusal, not a lookup.
        """
        bundle = self._spend(task_id, session_id=session_id, share_token=share_token)

        entry = next(
            (
                item
                for item in bundle.document["artifacts"]["files"]
                if item["name"] == name
            ),
            None,
        )
        if entry is None:
            raise ProofError(
                "Bu adda bir cikti bu gorevin calisma alaninda yok.",
                reason="artifact_missing",
            )
        if entry["content_state"] != BODY_EMBEDDED or not isinstance(
            entry["content"], str
        ):
            raise ProofError(
                str(entry["content_detail"]), reason="artifact_body_unavailable"
            )

        payload = str(entry["content"]).encode(CONTENT_ENCODING)
        stem, suffix = split_suffix(str(entry["name"]))
        return DeliveredArtifact(
            payload=payload,
            media_type=ARTIFACT_MEDIA_TYPE,
            filename=safe_download_filename(stem, suffix=suffix),
            name=str(entry["name"]),
            sha256=str(entry["sha256"]),
            bundle_sha256=bundle.sha256,
            delivered_at=datetime.now(UTC),
        )

    def discard_session(self, session_id: str) -> int:
        """Forget every approval belonging to a session that has ended.

        The composer's ``forget_session`` shape, including its honesty: no
        route calls this today. Sessions live only in process memory, so it
        fires on an explicit revocation rather than on a browser tab closing,
        and what actually enforces the property in between is the session
        binding checked at delivery time.
        """
        return self._approvals.discard_where(
            lambda approval: approval.session_id == session_id
        )

    # --- the two fields this package can fill ------------------------------

    def record_acceptance(
        self, task_id: str, *, bundle_sha256: str, detail: str = ""
    ) -> TaskView:
        """Record that a person accepted what the bundle showed.

        Bound to the bundle's digest, and the binding is checked here rather
        than trusted: an acceptance given for a bundle that has since changed
        is an acceptance of something else. That is the same rule the share
        approval follows, applied to the field that actually gates publication.

        ``verified=True`` is written **only** on this path, and this path is
        only reachable from an HTTP request a person made. No automatic route
        fills the field, and this method moves no state: the acceptance is the
        input to a publication decision, never its output (ADR-0009 8,
        SI-222).
        """
        bundle = self.build(task_id)
        if bundle.sha256 != bundle_sha256:
            raise ProofError(
                "Kabul, gorulen paketten farkli bir pakete ait; paket bu "
                "arada degisti. Yeni paketi okuyup tekrar kabul edin.",
                reason="bundle_changed",
            )

        sentence = self._acceptance_sentence(detail)
        return self._record(
            task_id,
            field=EvidenceField.USER_ACCEPTANCE,
            ref_id=bundle.sha256,
            verified=True,
            detail=sentence,
        )

    def record_public_share(
        self, task_id: str, *, evidence_id: str, detail: str = ""
    ) -> TaskView:
        """Mark the fourth field from an archived send, and only from one.

        Four things stand between a typed string and this field, and they do
        not all fire on this path. Naming them accurately matters more than
        counting them, because an adversarial review of H3 found the docstring
        that used to be here describing three checks of which two are
        unreachable from here:

        ``ProofPublicShareRequest.evidence_id`` (``min_length=32``)
            The HTTP shape gate. A caller who posts ``"paylasildi"`` gets a
            422 from the model and never reaches this function.

        :meth:`EvidenceService.get` - **the check that fires here**
            The archive read below. It is not a validation step bolted on: the
            record's ``write_outcome`` is an *input* to ``verified``, so the
            row has to be fetched before anything can be recorded. Every
            pointer that names no archived send stops here, whatever its
            shape, with ``evidence_record_missing``.

        :meth:`TaskService.record_evidence`'s row-existence check
            Reached only with a row that exists, so on this path it can only
            agree. It is depth for the callers that skip this service -
            ``record_evidence`` is public, and it is the only function in the
            product that writes these columns.

        :meth:`EvidenceRef.__post_init__`'s shape check
            Same: by the time it runs, the id came back from the archive's own
            primary key. It is what covers every place an ``EvidenceRef`` is
            built with no database at hand.

        So the two deeper checks are **defence in depth for callers that
        bypass this method**, not three independent refusals of one request.
        They are driven at their own level in ``tests/security``, because a
        defence that only ever runs behind another one is a defence nobody has
        watched work.
        """
        if self._evidence is None:
            raise ProofError(
                "Kanit arsivi bu makinede acilamadi; dis paylasim isareti "
                "arsivlenmis bir gonderime baglanamiyor.",
                reason="evidence_unavailable",
            )
        try:
            record = self._evidence.get(evidence_id)
        except EvidenceError as exc:
            raise ProofError(str(exc), reason="evidence_record_missing") from exc

        verified = record.write_outcome == ACCEPTED_WRITE_OUTCOME
        sentence = self._share_sentence(record.write_outcome, detail)
        return self._record(
            task_id,
            field=EvidenceField.PUBLIC_SHARE,
            ref_id=record.id,
            verified=verified,
            detail=sentence,
        )

    # --- helpers -----------------------------------------------------------

    def _record(
        self,
        task_id: str,
        *,
        field: EvidenceField,
        ref_id: str,
        verified: bool,
        detail: str,
    ) -> TaskView:
        try:
            return self._tasks.record_evidence(
                task_id,
                field=field,
                ref_id=ref_id,
                verified=verified,
                detail=detail,
            )
        except TaskError as exc:
            raise ProofError(str(exc), reason=exc.reason) from exc

    def _acceptance_sentence(self, detail: str) -> str:
        """Our sentence, with the user's own words neutralised first.

        The order is IMP-420's: the person's text is swept and neutralised,
        *then* joined to ours, *then* the joined sentence is checked. Checking
        first and laundering afterwards would make the guard a no-op, which is
        the mistake H2 made once and a test now watches for.
        """
        note = safe_text(detail)
        sentence = "Kullanici gorulen paketi acikca kabul etti."
        if note:
            sentence = f"{sentence} Kullanici notu: {note}"
        assert_no_forbidden_claim(sentence, where="proof acceptance detail")
        return sentence

    def _share_sentence(self, write_outcome: str, detail: str) -> str:
        note = safe_text(detail)
        sentence = (
            "Dis paylasim arsivlenmis bir gonderime baglandi; gonderim sonucu "
            f"'{safe_text(write_outcome)}'."
        )
        if write_outcome != ACCEPTED_WRITE_OUTCOME:
            sentence = (
                f"{sentence} Bu sonuc bir yayim onayi degildir, bu yuzden "
                "isaret dogrulanmamis olarak kaydedilir."
            )
        if note:
            sentence = f"{sentence} Kullanici notu: {note}"
        assert_no_forbidden_claim(sentence, where="proof public share detail")
        return sentence


__all__ = [
    "ACCEPTED_WRITE_OUTCOME",
    "ARTIFACT_MEDIA_TYPE",
    "DeliveredArtifact",
    "DeliveredBundle",
    "ProofError",
    "ProofService",
]
