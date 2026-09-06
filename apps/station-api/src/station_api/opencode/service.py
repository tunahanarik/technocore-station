"""The OpenCode connection service: store a credential, read a catalog, refuse honestly.

This is where the pieces meet, and where three promises are kept that no
single module below could keep on its own.

**The credential is registered for redaction for exactly as long as it is in
memory.** :func:`station_api.logging_setup.register_secret` on the way out of
the envelope, :func:`~station_api.logging_setup.forget_secret` in a
``finally``. The trap ADR-0005 8 names is that ``register_secret`` silently
ignores anything shorter than sixteen characters, so a short key would be
held and never scrubbed; :func:`~station_api.opencode.credential_store.
assert_storable` refuses one before it can be stored, and
:meth:`OpenCodeService._registered` asserts the length again at use time
rather than trusting that the store was the only way in.

**"Check the connection" sends one metered request, and only on a press.**
ADR-0005 4 said the check could produce no badge, and the reasoning under it
was right about everything except its own conclusion: the catalog answers
without a credential so fetching it verifies nothing, a ``GET`` on a protocol
path answers 404, and a metered call needs the user's explicit request. The
button *is* that request, and for five packages there was nothing behind it -
:meth:`check_connection` returned a constant. ADR-0015 puts a probe behind it:
:meth:`probe_connection`, one ``chat/completions`` turn with the stored
credential, **never** reached from :meth:`describe`, from a poll, or as a step
of storing a key. A format check is still deliberately absent: a key that
*looks* right would produce a green result that means nothing.

The verdict a probe produces is durable and per credential
(``opencode_probe_ledger``), so ``GET /api/opencode/status`` can report it
without repeating it, and so a spent ceiling cannot be handed back by
forgetting and re-saving the same key.

**Nothing is substituted.** :meth:`select_model` either resolves the id
through the closed table or refuses with the reason attached. There is no
fallback model, no nearest match and no silent rewrite.

Startup does nothing outbound. Building this service reads the database and
the envelope's existence; it sends no request, so a launch cannot cost money.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from station_api.agent.budget import MAX_CONNECTION_PROBES
from station_api.db.models import (
    AppMetadata,
    OpenCodeCatalogCheck,
    OpenCodeCredentialMetadata,
    OpenCodeModelSnapshot,
    OpenCodeProbeLedger,
)
from station_api.logging_setup import forget_secret, register_secret
from station_api.opencode import planner, probe
from station_api.opencode.catalog import (
    CatalogEntry,
    ModelView,
    build_views,
    parse_catalog,
)
from station_api.opencode.client import AUTH_HEADER_CAVEAT, OpenCodeClient
from station_api.opencode.credential_store import (
    CREDENTIAL_ID,
    MIN_KEY_LENGTH,
    ApiKeyEnvelope,
)
from station_api.opencode.errors import (
    CredentialEnvelopeError,
    ModelNotSelectableError,
    OpenCodeConfigurationError,
    OpenCodeError,
    OpenCodeLostResponseError,
    OpenCodeRequestError,
    OpenCodeResponseError,
)
from station_api.opencode.registry import (
    TABLE_PROVENANCE,
    ModelMapping,
    catalog_drift_notice,
    find_mapping,
    wire_model_id,
)

#: ``app_metadata`` key holding the chosen model. The selection lives in the
#: backend, never in browser storage (SI-24), and the value is a public model
#: identifier - which is why it can share a table whose contract is "never
#: holds a secret".
SELECTED_MODEL_KEY = "opencode.selected_model"

#: Longest catalog excerpt stored. Enough to recognise a document, far too
#: little to be a copy of it. Never returned over HTTP.
MAX_EXCERPT_CHARS = 4096

#: Number of catalog reads kept, matching ``snapshot.RETAINED_CHECKS``'s
#: reasoning: enough to review a change, small enough never to be a disk
#: problem.
RETAINED_CHECKS = 20


class CatalogState(StrEnum):
    """How the last catalog read ended."""

    NEVER_FETCHED = "never_fetched"
    OK = "ok"
    FETCH_ERROR = "fetch_error"
    PARSE_ERROR = "parse_error"


class VerificationState(StrEnum):
    """What can honestly be said about the stored credential.

    ``VERIFIED`` exists now, and the rule that kept it out is the reason it
    can: a value nothing could earn would be an invitation to set it from
    somewhere that had not earned it, and ADR-0015 gives it exactly one
    producer - a ``200`` from the metered endpoint, which no request without
    the credential can obtain.

    A probe produces **three** outcomes and each keeps its own value. Folding
    a refusal or an inconclusive answer back into ``SAVED_UNVERIFIED`` would
    make a failed check indistinguishable from a check nobody ran, which is
    the state this feature was written to leave behind.

    ``NEVER_CHECKED`` was removed. Nothing ever returned it, and the docstring
    that used to sit here warned - correctly - about exactly that kind of
    value.
    """

    NOT_CONFIGURED = "not_configured"
    #: A key is stored and no probe has been run against it.
    SAVED_UNVERIFIED = "key_saved_unverified"
    #: The provider answered the metered request. Only an accepted credential
    #: can produce this.
    VERIFIED = "verified"
    #: The provider answered and refused (401, or 403 for this model).
    PROVIDER_REFUSED = "provider_refused"
    #: No answer, or an answer that settles nothing. Not the same as refused,
    #: and deliberately not the same as unverified-because-nobody-asked.
    PROBE_FAILED = "probe_failed"


#: One probe outcome to one verdict, written out.
#:
#: The two enums carry the same three strings, so ``VerificationState(row.state)``
#: would have worked and would have coupled the wire value of a stored row to
#: the wire value of a verdict for as long as nobody edited either.
_STATE_FOR: dict[probe.ProbeOutcome, VerificationState] = {
    probe.ProbeOutcome.VERIFIED: VerificationState.VERIFIED,
    probe.ProbeOutcome.REFUSED: VerificationState.PROVIDER_REFUSED,
    probe.ProbeOutcome.FAILED: VerificationState.PROBE_FAILED,
}


@dataclass(frozen=True, slots=True)
class ConnectionCheck:
    """The result of "check the connection". A verdict, never a bare badge."""

    state: VerificationState
    #: Every reason the state is not stronger than it is. Plural on purpose,
    #: and pruned on purpose: a sentence that a probe made false is removed
    #: rather than left standing beside a fresh verdict.
    reasons: tuple[str, ...]
    detail: str
    #: When the last probe ran, or ``None`` when none has. A verification is a
    #: point-in-time fact and a badge with no date is one nobody can age.
    checked_at: datetime | None = None
    #: How many probes this credential has spent, and the ceiling it is spent
    #: against. Shown rather than only enforced: a limit a person meets by
    #: surprise is a limit they read as a bug.
    probes_used: int = 0
    probe_ceiling: int = MAX_CONNECTION_PROBES


@dataclass(frozen=True, slots=True)
class CatalogView:
    """The last catalog read, as the API layer will show it.

    Two timestamps, deliberately. ``fetched_at`` is the last *attempt* and
    ``models_fetched_at`` is when the listed models were actually read, so a
    failed refresh reports its failure without either deleting the cache or
    letting the cache borrow the failure's date. A single field would have
    forced one of those two lies (ADR-0005 5).
    """

    state: CatalogState
    fetched_at: datetime | None
    detail: str
    http_status: int
    models: tuple[ModelView, ...]
    models_fetched_at: datetime | None
    selectable_count: int
    #: How many listed models the pinned table has no row for. Shown as a
    #: number rather than only as per-row sentences, because the *count* is
    #: what says whether the table itself is behind.
    unmapped_count: int
    #: Always populated: when the protocol table was read, and what the
    #: source page's own footer said that day.
    table_provenance: str
    #: Empty while the catalog and the pinned table agree; a warning once the
    #: catalog lists more unmapped models than the transcription accounted
    #: for (:func:`catalog_drift_notice`).
    drift_notice: str


@dataclass(frozen=True, slots=True)
class ConnectionView:
    """Everything the status endpoint needs, and nothing that could leak."""

    configured: bool
    fingerprint_short: str
    configured_at: datetime | None
    updated_at: datetime | None
    check: ConnectionCheck
    selected_model: str
    catalog: CatalogView


_NOT_CONFIGURED_REASON = (
    "Saglayici anahtari kaydedilmedi. Baglanti kurulamaz."
)

_NOT_VERIFIABLE_REASON = (
    "Anahtar dogrulanmadi. Model katalogu anahtarsiz da yanit verdigi icin "
    "katalogu okumak anahtarin gecerli oldugunu kanitlamaz."
)

#: What replaced ``_NO_PROBE_REASON``.
#:
#: The old sentence ended "...ve henuz uygulanmamistir" - *and it has not been
#: implemented yet*. It was true when it was written and it was the thing the
#: button was hiding: a control that announced its own absence in a list most
#: people do not read. The probe exists now, so the sentence says what it
#: costs and what triggers it instead of apologising for not existing.
_PROBE_ON_REQUEST_REASON = (
    "Dogrulama yalnizca siz 'Baglantiyi denetle' dugmesine bastiginizda "
    "yapilir: secili modele, olculu ucta, tek bir kucuk model cagrisi "
    "gonderilir. Bu cagri sayilir ve anahtar basina bir tavani vardir."
)

#: What a verified verdict still does **not** say. Two bounds, both real.
_VERIFIED_SCOPE_REASON = (
    "Dogrulama tek bir cagriya ve kimlik dogrulamasina aittir: anahtarin "
    "sonraki cagrilarda da kabul edilecegini, kotanin dolu olmadigini veya "
    "baska bir modelin cagrilabilecegini kanitlamaz."
)

_REFUSED_REASON = (
    "Saglayici denetimi reddetti. Asagidaki cumle Station'in yorumu degil, "
    "saglayicinin yanitidir."
)

#: The "we do not know" verdict, and what it is careful not to claim.
_INCONCLUSIVE_REASON = (
    "Denetim sonuc vermedi: ya bir yanit gelmedi ya da gelen yanit anahtar "
    "hakkinda bir sey soylemiyor. Bu, anahtarin gecersiz oldugu anlamina "
    "gelmez."
)

_SAVED_DETAIL = (
    "Anahtar kaydedildi, dogrulanmadi. Dogrulamak icin 'Baglantiyi denetle' "
    "dugmesine basin; bu, secili modele olculu ucta tek bir model cagrisi "
    "gonderir."
)


def _ceiling_spent_reason(used: int) -> str:
    """The sentence a spent ceiling carries, with both numbers in it.

    Written as a function rather than a constant because ADR-0013 4's lesson
    was that a ceiling sentence which does not say where you stand is a
    sentence people argue with.
    """
    return (
        f"Bu anahtar icin denetim tavani doldu ({used}/{MAX_CONNECTION_PROBES}). "
        "Yeni bir denetim cagrisi yapilmaz ve sifirlama yolu yoktur. Baska bir "
        "anahtar kaydederseniz kendi tavaniyla baslar."
    )


class OpenCodeService:
    """Owns the credential envelope, the catalog cache and the model choice.

    ``client`` and ``mappings`` are test seams in the same sense the
    composer's ``signer`` and ``write_client`` are: neither can widen
    anything. The client's transport is narrowed to ``httpx.MockTransport``
    and its addresses come from the closed endpoint registry; an injected
    mapping table still resolves through the same four addresses because
    ``Protocol`` is a closed enum.
    """

    def __init__(
        self,
        *,
        engine: Engine | None,
        data_dir: Path,
        client: OpenCodeClient | None = None,
        mappings: tuple[ModelMapping, ...] | None = None,
    ) -> None:
        self._engine = engine
        self._envelope = ApiKeyEnvelope(data_dir)
        self._client = client
        self._mappings = mappings

    # --- credential --------------------------------------------------------

    def store_credential(self, api_key: str) -> ConnectionView:
        """Write the credential and record only metadata about it.

        Replaces an existing one, deliberately (ADR-0005 7). Registered for
        redaction across the whole call so an exception raised anywhere in
        here cannot carry the value into a log line.

        **The claim is withdrawn before it can become false.** The file and
        the metadata row are two writes with no transaction between them, and
        the order used to be file first: a database failure after a
        successful write left the row describing the *previous* key while the
        envelope held the new one, so ``/api/opencode/status`` answered
        "configured, ``9359c4e2``" about a key that was no longer there. The
        fingerprint is the only handle a user has on which key is stored
        (SI-242), so a fingerprint that is quietly wrong is worse than no
        fingerprint at all.

        Dropping the row first makes the wrong answer unreachable rather than
        unlikely. Every interruption now lands on one of:

        * the delete failed - nothing was written, the old row and the old
          envelope still agree;
        * the write failed - there is no row, so the connection reads as
          *not configured* even though a file may remain, which understates
          rather than misnames;
        * the insert failed - the new key is on disk and unnamed, and the
          connection again reads as *not configured*, so the user re-enters
          it instead of trusting a stale fingerprint.

        ``created_at`` is carried across the gap because it describes when
        the connection was first set up, not when this particular key was
        written; ``updated_at`` is what moves (SI-263).
        """
        self._require_engine()
        first_configured_at = self._withdraw_credential_row()

        with self._registered(api_key):
            fingerprint = self._envelope.store(api_key)

        now = datetime.now(UTC)
        with self._session() as session:
            session.add(
                OpenCodeCredentialMetadata(
                    id=CREDENTIAL_ID,
                    envelope_relpath=self._envelope.relpath(),
                    fingerprint=fingerprint,
                    created_at=first_configured_at or now,
                    updated_at=now,
                )
            )
            session.commit()
        return self.describe()

    def _withdraw_credential_row(self) -> datetime | None:
        """Remove the metadata row, returning the ``created_at`` it carried.

        Separate from :meth:`forget_credential` because it deletes only the
        claim, never the envelope: the file is about to be replaced, and
        removing it here would turn a failed write into data loss.
        """
        with self._session() as session:
            row = session.get(OpenCodeCredentialMetadata, CREDENTIAL_ID)
            first_configured_at = row.created_at if row is not None else None
            if row is not None:
                session.delete(row)
                session.commit()
        return first_configured_at

    def forget_credential(self) -> ConnectionView:
        """Remove the envelope and its metadata row.

        The catalog cache and the model choice survive: neither was derived
        from the credential, and deleting a public model list because a key
        went away would be a side effect nobody asked for. What does change
        is the verification state, which drops back to ``not_configured``.
        """
        self._require_engine()
        self._envelope.delete()
        with self._session() as session:
            session.execute(
                delete(OpenCodeCredentialMetadata).where(
                    OpenCodeCredentialMetadata.id == CREDENTIAL_ID
                )
            )
            session.commit()
        return self.describe()

    # --- status ------------------------------------------------------------

    def describe(self) -> ConnectionView:
        """The whole read-only picture. Sends nothing."""
        row = self._credential_row()
        configured = row is not None and self._envelope.exists()
        # Every metadata field is gated on ``configured``, not merely on the
        # row existing. A row without an envelope describes a key that is not
        # there, and showing its fingerprint beside "not configured" would be
        # the same wrong answer in a quieter voice.
        return ConnectionView(
            configured=configured,
            fingerprint_short=row.fingerprint[:12] if configured and row else "",
            configured_at=row.created_at if configured and row else None,
            updated_at=row.updated_at if configured and row else None,
            check=self.check_connection(),
            selected_model=self._selected_model(),
            catalog=self.catalog_view(),
        )

    def check_connection(self) -> ConnectionCheck:
        """The stored verdict, and every reason it is not stronger. **Sends nothing.**

        This reads: the credential row, and the probe ledger row keyed to that
        credential's fingerprint. It is reached from :meth:`describe`, which is
        reached from ``GET /api/opencode/status``, which is reached on page
        load - so a request from here would be a metered call on a page load,
        which is the one thing ADR-0005 4 was right about and ADR-0015 does not
        change. The probe is :meth:`probe_connection` and nothing calls it but
        its own route.

        The reasons are assembled per state rather than shared, because they
        are not all true in every state. ``_NOT_VERIFIABLE_REASON`` opens with
        *anahtar dogrulanmadi* and is dropped the moment a probe succeeds;
        :data:`~station_api.opencode.client.AUTH_HEADER_CAVEAT` survives every
        state, because "the header works and the documentation still does not
        publish it" is as true after a green verdict as before one.
        """
        row = self._credential_row()
        if not (row is not None and self._envelope.exists()):
            return ConnectionCheck(
                state=VerificationState.NOT_CONFIGURED,
                reasons=(_NOT_CONFIGURED_REASON,),
                detail=_NOT_CONFIGURED_REASON,
            )

        ledger = self._probe_row(row.fingerprint)
        if ledger is None:
            return ConnectionCheck(
                state=VerificationState.SAVED_UNVERIFIED,
                reasons=(
                    _NOT_VERIFIABLE_REASON,
                    _PROBE_ON_REQUEST_REASON,
                    AUTH_HEADER_CAVEAT,
                ),
                detail=_SAVED_DETAIL,
            )

        outcome = probe.ProbeOutcome(ledger.state)
        if outcome is probe.ProbeOutcome.VERIFIED:
            reasons = [_VERIFIED_SCOPE_REASON, AUTH_HEADER_CAVEAT]
        elif outcome is probe.ProbeOutcome.REFUSED:
            reasons = [_REFUSED_REASON, _NOT_VERIFIABLE_REASON, AUTH_HEADER_CAVEAT]
        else:
            reasons = [_INCONCLUSIVE_REASON, _NOT_VERIFIABLE_REASON, AUTH_HEADER_CAVEAT]
        if ledger.probes_used >= MAX_CONNECTION_PROBES:
            reasons.append(_ceiling_spent_reason(ledger.probes_used))

        return ConnectionCheck(
            state=_STATE_FOR[outcome],
            reasons=tuple(reasons),
            detail=ledger.detail,
            checked_at=ledger.last_probe_at,
            probes_used=ledger.probes_used,
        )

    def probe_connection(self) -> ConnectionView:
        """Send **one** metered request to prove the stored key authenticates.

        The only method in this class that spends money on a credential's
        behalf other than :meth:`propose_plan`, and the only one a person
        reaches by pressing "Baglantiyi denetle". It is called from exactly one
        route and from nowhere else: not from :meth:`describe`, not from
        :meth:`store_credential`, not from a timer, and there is no timer.

        Everything that could go wrong before money is spent is refused before
        the request is built, and each refusal is its own sentence:

        * **no credential** - there is nothing to authenticate with, and a
          probe without one would be measuring the network;
        * **the probe ceiling for this credential is spent** - nothing is
          sent, the stored verdict stands, and the reasons list already says
          so. This returns rather than raises because a spent ceiling is a
          *state of the connection*, not an error in the request, which is the
          same call :meth:`refresh_catalog` makes about a failed fetch;
        * **no selected model** - Station does not pick one (ADR-0005 11), and
          picking a default *for* a verification would be the substitution rule
          broken in the one place a person would never look for it;
        * **a model whose row is not selectable, or whose protocol family is
          not the measured one.** The probe body is ``chat/completions``
          shaped because that is the shape ADR-0012 measured; a ``responses``
          model is refused by name rather than probed against an unread
          contract.

        The credential is held in the redaction registry for exactly the
        duration of the call - :meth:`ApiKeyEnvelope.opened` takes that choice
        away from this method - and the client registers it a second time
        around the response excerpt, which is where a reflected key would
        otherwise appear.

        **A lost answer counts.** ADR-0013 3 counts a planning turn only once
        a provider answer has been parsed, and that is right for a lane where a
        person is watching a session unfold. Here the ceiling is the only thing
        between a button and a metered endpoint, and
        :class:`~station_api.opencode.errors.OpenCodeLostResponseError` means
        precisely *this request may already have been billed*. A ceiling that
        hands back a maybe-billed call is a ceiling with a retry loop in it, so
        every attempt that reached the client is counted.
        """
        self._require_engine()
        row = self._credential_row()
        if not (row is not None and self._envelope.exists()):
            raise OpenCodeConfigurationError(
                "Saglayici anahtari kaydedilmedi; baglanti denetlenemez."
            )
        fingerprint = row.fingerprint

        ledger = self._probe_row(fingerprint)
        if ledger is not None and ledger.probes_used >= MAX_CONNECTION_PROBES:
            return self.describe()

        selected = self._selected_model()
        if not selected:
            raise ModelNotSelectableError(
                "Bir model secilmedi. Denetim, secilen modele gercek bir cagri "
                "gonderir; Station sizin yerinize model secmez."
            )
        mapping = find_mapping(selected, mappings=self._mappings)
        if mapping is None or not mapping.selectable:
            raise ModelNotSelectableError(
                f"'{selected}' bu surumun pinli tablosunda secilebilir "
                "degil; denetim cagrisi yapilmaz ve baska bir modele gecilmez."
            )
        if mapping.protocol is not probe.PROBE_PROTOCOL:
            raise ModelNotSelectableError(
                f"'{selected}' modelinin protokol ailesi "
                f"'{mapping.protocol.value}'. Denetim istegi yalnizca "
                f"'{probe.PROBE_PROTOCOL.value}' ailesi icin olculdu; "
                "digerleri icin tahmin edilmez."
            )

        body = probe.build_probe_request(model=mapping.wire_id)
        client = self._client if self._client is not None else OpenCodeClient()
        with self._envelope.opened() as api_key:
            try:
                raw = client.post_completion(
                    probe.PROBE_PROTOCOL, body, api_key=api_key
                )
            except OpenCodeLostResponseError as exc:
                result = probe.lost(str(exc))
            except OpenCodeRequestError as exc:
                result = probe.transport_failed(str(exc))
            else:
                result = probe.classify(raw)

        self._record_probe(fingerprint, result)
        return self.describe()

    # --- catalog -----------------------------------------------------------

    def refresh_catalog(self) -> CatalogView:
        """Fetch the public catalog. **Only on the user's request.**

        No credential is attached, because none is required. The rows written
        carry the compile-time protocol table's verdict, not the document's:
        a fetched catalog cannot make a model addressable.
        """
        self._require_engine()
        client = self._client if self._client is not None else OpenCodeClient()

        now = datetime.now(UTC)
        try:
            raw = client.fetch_catalog()
        except OpenCodeRequestError as exc:
            self._record_check(
                state=CatalogState.FETCH_ERROR,
                fetched_at=now,
                detail=str(exc),
                http_status=0,
                content_sha256="",
                byte_count=0,
                entries=(),
                excerpt="",
            )
            return self.catalog_view()

        try:
            entries = parse_catalog(raw)
        except OpenCodeResponseError as exc:
            self._record_check(
                state=CatalogState.PARSE_ERROR,
                fetched_at=now,
                detail=str(exc),
                http_status=raw.status_code,
                content_sha256=raw.sha256,
                byte_count=raw.byte_count,
                entries=(),
                excerpt=raw.excerpt[:MAX_EXCERPT_CHARS],
            )
            return self.catalog_view()

        self._record_check(
            state=CatalogState.OK,
            fetched_at=now,
            detail="",
            http_status=raw.status_code,
            content_sha256=raw.sha256,
            byte_count=raw.byte_count,
            entries=entries,
            excerpt=raw.excerpt[:MAX_EXCERPT_CHARS],
        )
        return self.catalog_view()

    def catalog_view(self) -> CatalogView:
        """The cached catalog, with its own age and the last attempt's error.

        A failed refresh does **not** delete the cache and does not lend it
        its own timestamp: the state and the error come from the newest
        attempt, the list and its date come from the newest attempt that
        actually read a document. Collapsing those would either hide an
        outage or throw away a list the user can still read honestly.
        """
        empty = CatalogView(
            state=CatalogState.NEVER_FETCHED,
            fetched_at=None,
            detail="",
            http_status=0,
            models=(),
            models_fetched_at=None,
            selectable_count=0,
            unmapped_count=0,
            # Present even before anything was fetched: the table's age is a
            # property of this build, not of a reading.
            table_provenance=TABLE_PROVENANCE,
            drift_notice="",
        )
        if self._engine is None:
            return empty

        with self._session() as session:
            check = session.scalars(
                select(OpenCodeCatalogCheck).order_by(
                    OpenCodeCatalogCheck.fetched_at.desc()
                )
            ).first()
            if check is None:
                return empty
            successful = session.scalars(
                select(OpenCodeCatalogCheck)
                .where(OpenCodeCatalogCheck.state == CatalogState.OK.value)
                .order_by(OpenCodeCatalogCheck.fetched_at.desc())
            ).first()
            rows = (
                session.scalars(
                    select(OpenCodeModelSnapshot)
                    .where(OpenCodeModelSnapshot.check_id == successful.id)
                    .order_by(OpenCodeModelSnapshot.model_id)
                ).all()
                if successful is not None
                else []
            )
            entries = tuple(
                CatalogEntry(
                    model_id=row.model_id,
                    owned_by=row.owned_by,
                    created=row.created_stamp,
                )
                for row in rows
            )
            state = CatalogState(check.state)
            fetched_at = check.fetched_at
            detail = check.detail
            http_status = check.http_status
            models_fetched_at = successful.fetched_at if successful is not None else None

        # Re-joined from the compile-time table on every read rather than
        # trusted from the stored row: the table is the authority, and a
        # build whose table changed must not keep showing yesterday's verdict.
        views = build_views(entries, mappings=self._mappings)
        # A model with no protocol at all is one the pinned table has no row
        # for; an unselectable model with a protocol is a row that exists and
        # was never published. Only the first kind says anything about the
        # table being behind the source page, so only the first kind counts.
        unmapped = sum(1 for view in views if view.protocol == "")
        return CatalogView(
            state=state,
            fetched_at=fetched_at,
            detail=detail,
            http_status=http_status,
            models=views,
            models_fetched_at=models_fetched_at,
            selectable_count=sum(1 for view in views if view.selectable),
            unmapped_count=unmapped,
            table_provenance=TABLE_PROVENANCE,
            drift_notice=catalog_drift_notice(
                listed_count=len(views), unmapped_count=unmapped
            ),
        )

    # --- model choice ------------------------------------------------------

    def select_model(
        self, model_id: str, *, training_acknowledged: bool = False
    ) -> str:
        """Choose a model, or refuse and say why.

        Never substitutes. A model with no table entry, or with an entry
        whose protocol family the documentation never published, is refused
        with the reason attached - the user's choice is not quietly turned
        into another model's (ADR-0005 11).
        """
        self._require_engine()
        bare = wire_model_id(model_id.strip())
        mapping = find_mapping(bare, mappings=self._mappings)
        if mapping is None:
            raise ModelNotSelectableError(
                f"'{bare}' icin bu surumun pinli tablosunda esleme yok. "
                "Listeleniyor olabilir ama secilemez; Station baska bir "
                "modele gecmez."
            )
        if not mapping.selectable:
            raise ModelNotSelectableError(
                f"'{bare}' modelinin protokol ailesi bu surumun pinli "
                "tablosunda bos. Tahmin edilmedi, bu yuzden secilemez."
            )
        if mapping.requires_training_acknowledgement and not training_acknowledged:
            raise ModelNotSelectableError(
                f"'{bare}' icin veri saklama/egitim kosulu "
                f"'{mapping.training_use.value}'. Bu model varsayilan olarak "
                "secilemez; devam etmek icin ayrica onaylamaniz gerekir."
            )

        with self._session() as session:
            row = session.get(AppMetadata, SELECTED_MODEL_KEY)
            now = datetime.now(UTC)
            if row is None:
                session.add(
                    AppMetadata(key=SELECTED_MODEL_KEY, value=bare, updated_at=now)
                )
            else:
                row.value = bare
                row.updated_at = now
            session.commit()
        return bare

    # --- the metered lane --------------------------------------------------

    def propose_plan(
        self,
        *,
        messages: tuple[planner.Message, ...],
        functions: tuple[planner.ToolFunction, ...],
        max_output_tokens: int,
    ) -> planner.PlanProposal:
        """Ask the selected model for one turn. **The only metered call here.**

        Everything that could go wrong before money is spent is refused
        before the request is built, and each refusal is its own sentence:

        * no credential - there is nothing to authenticate with;
        * no selected model - Station does not pick one. ADR-0005 11's rule is
          that nothing is ever substituted, and choosing a default *for* the
          user is the same substitution with a friendlier name;
        * a model whose row in the closed table is not selectable, or whose
          protocol family is not the one whose tool-call shape was
          **measured**. The measurement covers ``chat/completions`` and
          nothing else, so a ``responses`` or ``messages`` model is refused by
          name rather than sent to a contract nobody has read.

        The credential is held in the redaction registry for exactly the
        duration of the call - :meth:`ApiKeyEnvelope.opened` takes that choice
        away from this method - and the client registers it a second time
        around the response excerpt, which is where a reflected key would
        otherwise appear.

        One attempt, never two. :meth:`OpenCodeClient.post_completion` turns a
        lost response into :class:`OpenCodeLostResponseError` because a
        request that left the process may already have been billed, and this
        turns that into a stated failure rather than a retry.

        ``max_output_tokens`` has **no default**, deliberately. It used to
        carry one, and a caller that never mentioned it therefore got a
        ceiling nobody in the calling lane had thought about - which is how a
        live planning turn came to be cut off at 1024 tokens with nothing in
        the calling code naming that number. A required argument makes the
        ceiling a decision the lane spending the money states out loud, and
        makes forgetting it a build error rather than a truncation a person
        discovers.
        """
        self._require_engine()
        if not (self._credential_row() is not None and self._envelope.exists()):
            raise OpenCodeConfigurationError(
                "Saglayici anahtari kaydedilmedi; model cagrisi yapilamaz."
            )
        selected = self._selected_model()
        if not selected:
            raise ModelNotSelectableError(
                "Bir model secilmedi. Station sizin yerinize model secmez; "
                "listeden birini secin."
            )
        mapping = find_mapping(selected, mappings=self._mappings)
        if mapping is None or not mapping.selectable:
            raise ModelNotSelectableError(
                f"'{selected}' bu surumun pinli tablosunda secilebilir "
                "degil; model cagrisi yapilmaz ve baska bir modele gecilmez."
            )
        if mapping.protocol is not planner.SUPPORTED_PROTOCOL:
            raise ModelNotSelectableError(
                f"'{selected}' modelinin protokol ailesi "
                f"'{mapping.protocol.value}'. Arac cagrisi bicimi yalnizca "
                f"'{planner.SUPPORTED_PROTOCOL.value}' ailesi icin olculdu; "
                "digerleri icin tahmin edilmez."
            )

        body = planner.build_plan_request(
            model=mapping.wire_id,
            messages=messages,
            functions=functions,
            max_output_tokens=max_output_tokens,
        )
        client = self._client if self._client is not None else OpenCodeClient()
        with self._envelope.opened() as api_key:
            try:
                raw = client.post_completion(
                    planner.SUPPORTED_PROTOCOL, body, api_key=api_key
                )
            except OpenCodeLostResponseError as exc:
                return planner.lost(str(exc))
            except OpenCodeRequestError as exc:
                return planner.transport_failed(str(exc))
        return planner.parse_plan_response(raw)

    # --- internals ---------------------------------------------------------

    @contextmanager
    def _registered(self, api_key: str) -> Iterator[None]:
        """Hold the credential in the redaction registry for one operation.

        The length is re-checked here and not only at the store boundary.
        ``register_secret`` ignores anything under sixteen characters without
        saying so, and a value it ignored would be a value nothing scrubs -
        so this refuses rather than proceeding with a broken promise.
        """
        if len(api_key) < MIN_KEY_LENGTH:
            raise CredentialEnvelopeError(
                "anahtar redaksiyon icin gereken en kisa uzunlugun altinda"
            )
        register_secret(api_key)
        try:
            yield
        finally:
            forget_secret(api_key)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        engine = self._require_engine()
        with Session(engine) as session:
            yield session

    def _require_engine(self) -> Engine:
        if self._engine is None:
            raise OpenCodeConfigurationError("veritabani kullanilabilir degil")
        return self._engine

    def _credential_row(self) -> OpenCodeCredentialMetadata | None:
        if self._engine is None:
            return None
        with self._session() as session:
            return session.get(OpenCodeCredentialMetadata, CREDENTIAL_ID)

    def _probe_row(self, fingerprint: str) -> OpenCodeProbeLedger | None:
        """This credential's probe ledger row. A read; writes nothing."""
        if self._engine is None:
            return None
        with self._session() as session:
            return session.get(OpenCodeProbeLedger, fingerprint)

    def _record_probe(self, fingerprint: str, result: probe.ProbeResult) -> None:
        """Count one probe against this credential and store what it answered.

        The **only** writer of ``probes_used`` in this build, and it only adds.
        There is no reset, no setter and no argument that could make the count
        go down; ``test_opencode_probe.py::
        test_nothing_lowers_the_connection_probe_counter`` reads the syntax
        tree of the whole package tree to keep it that way, and its companion
        keeps the row from being deleted - deleting a row lowers a counter just
        as effectively as assigning to it, which is the mutation ADR-0013 5
        found the hard way.

        The verdict columns are replaced on every probe. That is the point of
        them: a failed check must not leave the previous verdict standing, and
        a stale ``verified`` beside a fresh refusal is the exact shape of
        dishonesty this feature exists to remove.
        """
        now = datetime.now(UTC)
        detail = result.detail[:MAX_EXCERPT_CHARS]
        with self._session() as session, session.begin():
            row = session.get(OpenCodeProbeLedger, fingerprint)
            if row is None:
                session.add(
                    OpenCodeProbeLedger(
                        fingerprint=fingerprint,
                        probes_used=1,
                        first_probe_at=now,
                        last_probe_at=now,
                        state=result.outcome.value,
                        http_status=result.http_status,
                        detail=detail,
                    )
                )
            else:
                row.probes_used += 1
                row.last_probe_at = now
                row.state = result.outcome.value
                row.http_status = result.http_status
                row.detail = detail

    def _selected_model(self) -> str:
        if self._engine is None:
            return ""
        with self._session() as session:
            row = session.get(AppMetadata, SELECTED_MODEL_KEY)
            return row.value if row is not None else ""

    def _record_check(
        self,
        *,
        state: CatalogState,
        fetched_at: datetime,
        detail: str,
        http_status: int,
        content_sha256: str,
        byte_count: int,
        entries: tuple[CatalogEntry, ...],
        excerpt: str,
    ) -> None:
        views = build_views(entries, mappings=self._mappings)
        check_id = uuid.uuid4().hex
        with self._session() as session:
            session.add(
                OpenCodeCatalogCheck(
                    id=check_id,
                    fetched_at=fetched_at,
                    state=state.value,
                    detail=detail[:MAX_EXCERPT_CHARS],
                    http_status=http_status,
                    content_sha256=content_sha256,
                    byte_count=byte_count,
                    model_count=len(views),
                    snapshot_excerpt=excerpt,
                )
            )
            for view in views:
                entry = next(e for e in entries if e.model_id == view.model_id)
                session.add(
                    OpenCodeModelSnapshot(
                        id=uuid.uuid4().hex,
                        check_id=check_id,
                        model_id=view.model_id,
                        owned_by=view.owned_by,
                        created_stamp=entry.created,
                        selectable=view.selectable,
                        protocol=view.protocol,
                        mapping_state=view.protocol_verification,
                        training_use=view.training_use,
                    )
                )
            # Flushed first so the pruning window below counts the read that
            # just happened; otherwise the newest row is invisible to the
            # ordering and the cache keeps one more than it says it does.
            session.flush()
            self._prune(session)
            session.commit()

    def _prune(self, session: Session) -> None:
        """Keep the last :data:`RETAINED_CHECKS` reads.

        Unlike the evidence archive - which is never pruned, because it is
        evidence - this is a cache of a public document that can be fetched
        again. Bounding it keeps a repeatedly-pressed button from becoming a
        disk problem.
        """
        keep = session.scalars(
            select(OpenCodeCatalogCheck.id)
            .order_by(OpenCodeCatalogCheck.fetched_at.desc())
            .limit(RETAINED_CHECKS)
        ).all()
        if not keep:
            return
        session.execute(
            delete(OpenCodeCatalogCheck).where(
                OpenCodeCatalogCheck.id.notin_(list(keep))
            )
        )


__all__ = [
    "MAX_EXCERPT_CHARS",
    "RETAINED_CHECKS",
    "SELECTED_MODEL_KEY",
    "CatalogState",
    "CatalogView",
    "ConnectionCheck",
    "ConnectionView",
    "OpenCodeError",
    "OpenCodeService",
    "VerificationState",
]
