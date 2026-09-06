"""The connection probe: the button that said something and did nothing.

A user saved a provider key, pressed **"Baglantiyi denetle"**, and the badge
stayed "Anahtar kaydedildi, dogrulanmadi" - forever, whatever the provider
would have answered. Two halves were missing and each one alone was enough:
``OpenCodeService.check_connection`` returned a **static** verdict, and the
panel's check button called ``GET /api/opencode/status``, which is the same
read the page already did on mount.

This file drives the user-visible half first. The primary test below stores a
credential, points a mock transport at a provider that accepts it, invokes the
check, and requires the verdict to be able to reach ``VERIFIED``. Nothing else
in this file matters if that one can be deleted without going red.

The rest holds the four things a probe must not become
------------------------------------------------------
* **a page-load cost.** ``describe``, ``store_credential`` and
  ``GET /api/opencode/status`` send nothing, and the transport recorder is
  what says so rather than a comment;
* **an uncounted model call.** ADR-0013 made the model-call count the only
  spend control this product owns, and a metered call nothing counts is a way
  around it. The count is per credential, durable, monotonic and has no reset -
  which is asserted behaviourally *and* against the syntax tree, because a
  behavioural test can only say the reset paths that exist today do not exist;
* **a badge that outlives its evidence.** A failed probe replaces a verified
  verdict rather than leaving it standing, and every sentence a probe makes
  false is dropped from the reasons list;
* **a way out for the credential.** The probe is the one operation that sends
  the key to the provider on purpose, so the planted-canary test below asserts
  it reaches neither the verdict, nor the stored row, nor the database file.

**No test here makes a real request.** Every client is driven through an
``httpx.MockTransport`` and the autouse guard in ``tests/conftest.py`` blocks
the network underneath it (SI-174). The credential is the synthetic
``TEST_ONLY_`` value, imported rather than written out so
``test_opencode_leakage.py``'s canary scan stays meaningful.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, inspect
from station_api.agent.budget import MAX_CONNECTION_PROBES
from station_api.config import Settings
from station_api.opencode.client import AUTH_HEADER_CAVEAT, OpenCodeClient
from station_api.opencode.errors import (
    ModelNotSelectableError,
    OpenCodeConfigurationError,
)
from station_api.opencode.probe import (
    PROBE_MAX_OUTPUT_TOKENS,
    PROBE_PROMPT,
    ProbeOutcome,
)
from station_api.opencode.service import OpenCodeService, VerificationState

from tests.conftest import TEST_ONLY_OPENCODE_CREDENTIAL
from tests.security.opencode_fixtures import (
    CHAT_COMPLETIONS_BODY,
    OBSERVED_MODEL_ID,
    SECOND_OBSERVED_MODEL_ID,
    never_called_transport,
    recording_transport,
    refusing_transport,
    status_transport,
)

pytestmark = pytest.mark.security

#: A second synthetic key, so "a different credential gets its own ceiling"
#: can be driven without reusing the canary the leakage file scans for.
SECOND_TEST_ONLY_CREDENTIAL = "TEST-ONLY-oc-second-key-0000000000-NOT-REAL"

#: The one place ``probes_used`` may be written, as ``file:function``.
THE_ONLY_PROBE_COUNTER_WRITE = "service.py:_record_probe"


def _accepting_transport(document: dict[str, Any] | None = None):  # type: ignore[no-untyped-def]
    """A provider that answers ``200`` to the metered request, as measured."""
    body = json.dumps(document if document is not None else CHAT_COMPLETIONS_BODY)
    return recording_transport(
        lambda _: httpx.Response(
            200, content=body.encode(), headers={"content-type": "application/json"}
        )
    )


def _service(  # type: ignore[no-untyped-def]
    engine: Engine, settings: Settings, transport: httpx.MockTransport
):
    return OpenCodeService(
        engine=engine,
        data_dir=settings.data_dir,
        client=OpenCodeClient(transport=transport, sleep=lambda _: None),
    )


def _connected(  # type: ignore[no-untyped-def]
    engine: Engine,
    settings: Settings,
    transport: httpx.MockTransport,
    *,
    credential: str = TEST_ONLY_OPENCODE_CREDENTIAL,
    model: str = OBSERVED_MODEL_ID,
):
    """A service with a synthetic key stored and a documented model chosen."""
    service = _service(engine, settings, transport)
    service.store_credential(credential)
    if model:
        service.select_model(model)
    return service


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------


def test_a_saved_key_can_reach_a_verified_verdict_when_the_provider_accepts_it(
    engine: Engine, settings: Settings
) -> None:
    """The defect, driven from the user's side.

    A key is stored, a model is chosen, the provider accepts the credential at
    the metered endpoint - which is the one thing that cannot happen without
    it - and the check is invoked the way the button invokes it. The verdict
    has to be able to say so.

    Before the fix this fails whatever the transport answers: there was no
    probe to invoke, and ``check_connection`` returned
    ``key_saved_unverified`` from a branch that read no provider answer at all.
    """
    transport, recorder = _accepting_transport()
    service = _connected(engine, settings, transport)

    view = service.probe_connection()

    assert view.check.state is VerificationState.VERIFIED
    assert recorder.count == 1


def test_the_verdict_vocabulary_has_a_word_for_an_accepted_key() -> None:
    """The other half of the same defect, stated as a type.

    ``VerificationState`` had no value meaning "the provider accepted this
    key", and its docstring said the absence was deliberate because nothing in
    the build could earn one. A probe earns one. A vocabulary with no word for
    the outcome cannot report the outcome, so this is asserted separately from
    the behaviour above: the behaviour test would have failed on a missing
    method and said nothing about the missing word.
    """
    assert "VERIFIED" in VerificationState.__members__


def test_the_verdict_survives_a_status_read_and_carries_its_own_date(
    engine: Engine, settings: Settings
) -> None:
    """A probe is worth nothing if the next read forgets it.

    The panel re-reads ``describe`` on mount, so a verdict that lived only in
    the probe's own reply would put the badge back to "unverified" on the next
    render - the original defect with an extra step.
    """
    transport, _ = _accepting_transport()
    service = _connected(engine, settings, transport)
    service.probe_connection()

    check = service.describe().check

    assert check.state is VerificationState.VERIFIED
    assert check.checked_at is not None
    assert check.probes_used == 1
    assert check.probe_ceiling == MAX_CONNECTION_PROBES


# ---------------------------------------------------------------------------
# Explicit press only
# ---------------------------------------------------------------------------


def test_reading_the_status_sends_nothing(engine: Engine, settings: Settings) -> None:
    """``GET /api/opencode/status`` must stay free of the probe.

    Driven with a transport that raises on any request, so the claim is
    measured rather than asserted about a count that could be zero for another
    reason - and the count is checked too, which distinguishes "nothing was
    attempted" from "the assertion never ran".
    """
    transport, recorder = never_called_transport()
    service = _service(engine, settings, transport)
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)
    service.select_model(OBSERVED_MODEL_ID)

    for _ in range(3):
        view = service.describe()
        service.check_connection()

    assert recorder.count == 0
    assert view.check.state is VerificationState.SAVED_UNVERIFIED


def test_storing_a_key_does_not_probe_it(engine: Engine, settings: Settings) -> None:
    """Saving is not checking. A store that probed would spend on a keystroke."""
    transport, recorder = never_called_transport()
    service = _service(engine, settings, transport)

    view = service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)

    assert recorder.count == 0
    assert view.check.state is VerificationState.SAVED_UNVERIFIED
    assert view.check.probes_used == 0


def test_a_catalog_refresh_is_not_a_probe(engine: Engine, settings: Settings) -> None:
    """The reason the catalog can never serve as the probe, kept as a test.

    ``fetch_catalog`` attaches no credential, so a successful refresh says
    nothing about the key - and it must not move the verdict either.
    """
    transport, _ = recording_transport(
        lambda _: httpx.Response(
            200,
            content=json.dumps({"object": "list", "data": []}).encode(),
            headers={"content-type": "application/json"},
        )
    )
    service = _service(engine, settings, transport)
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)

    service.refresh_catalog()
    check = service.describe().check

    assert check.state is VerificationState.SAVED_UNVERIFIED
    assert check.probes_used == 0


def test_the_probe_request_carries_the_credential_and_no_tool_registry(
    engine: Engine, settings: Settings
) -> None:
    """What actually goes on the wire: the measured shape, and nothing extra.

    The tool registry is what a *plan* offers a model. A connection check
    offering it would put the whole capability surface on a lane whose only
    question is whether a header is accepted.
    """
    transport, recorder = _accepting_transport()
    service = _connected(engine, settings, transport)

    service.probe_connection()

    request = recorder.last
    assert request.method == "POST"
    assert str(request.url).endswith("/chat/completions")
    assert request.headers["authorization"] == f"Bearer {TEST_ONLY_OPENCODE_CREDENTIAL}"
    body = json.loads(request.content.decode())
    assert body["model"] == OBSERVED_MODEL_ID
    assert body["max_tokens"] == PROBE_MAX_OUTPUT_TOKENS
    assert body["messages"] == [{"role": "user", "content": PROBE_PROMPT}]
    assert body["stream"] is False
    assert "tools" not in body
    assert "tool_choice" not in body


# ---------------------------------------------------------------------------
# What each answer means
# ---------------------------------------------------------------------------


def test_a_rejected_credential_is_its_own_verdict(
    engine: Engine, settings: Settings
) -> None:
    """401 is a refusal, and a refusal must not read like an unasked question."""
    transport, _ = status_transport(401, body=b'{"error": {"message": "no"}}')
    service = _connected(engine, settings, transport)

    view = service.probe_connection()

    assert view.check.state is VerificationState.PROVIDER_REFUSED
    assert "401" in view.check.detail
    assert view.check.probes_used == 1


def test_a_forbidden_model_is_reported_as_the_provider_stated_it(
    engine: Engine, settings: Settings
) -> None:
    """403 is the account being refused this model, not proof the key is wrong.

    The state is the same refusal - the provider looked and said no - and the
    sentence beside it is the one that distinguishes them, which is why the
    sentence is asserted rather than only the state.
    """
    transport, _ = status_transport(403, body=b"{}")
    service = _connected(engine, settings, transport)

    detail = service.probe_connection().check.detail

    assert "403" in detail
    assert "listelenmesi" in detail


@pytest.mark.parametrize(
    "status_code,body",
    [
        (429, b"{}"),
        (500, b"{}"),
        (404, b"{}"),
        (200, b'{"error": {"message": "TEST-ONLY"}}'),
        (200, b"not json at all"),
        (200, b"   "),
    ],
)
def test_an_answer_that_settles_nothing_is_neither_verified_nor_refused(
    engine: Engine, settings: Settings, status_code: int, body: bytes
) -> None:
    """The third outcome, driven through every shape that reaches it.

    A 429 and a 500 are answers from a host that was plainly reached, which is
    why the state is not called "unreachable"; a ``200`` carrying an ``error``
    member is the case a status-only reader gets wrong; an unparseable or
    empty body is not an empty answer.
    """
    transport, _ = status_transport(status_code, body=body)
    service = _connected(engine, settings, transport)

    view = service.probe_connection()

    assert view.check.state is VerificationState.PROBE_FAILED
    assert view.check.detail != ""


def test_a_lost_answer_is_inconclusive_and_is_still_counted(
    engine: Engine, settings: Settings
) -> None:
    """The one failure that may already have been billed.

    ADR-0013 3 counts a planning turn only after an answer is parsed. Here the
    ceiling is the only thing between a button and a metered endpoint, so a
    request that left the process counts even though its answer never came
    back - otherwise a timeout is a free press.
    """
    transport, _ = refusing_transport(httpx.ConnectError("simulated"))
    service = _connected(engine, settings, transport)

    view = service.probe_connection()

    assert view.check.state is VerificationState.PROBE_FAILED
    assert view.check.probes_used == 1


def test_a_failed_probe_replaces_a_verified_verdict_rather_than_leaving_it(
    engine: Engine, settings: Settings
) -> None:
    """The stale-badge rule, driven in the direction that matters.

    A green badge left standing beside a fresh refusal is worse than no badge:
    it is the product asserting something it has just been told is not true.
    """
    good, _ = _accepting_transport()
    service = _connected(engine, settings, good)
    service.probe_connection()
    assert service.describe().check.state is VerificationState.VERIFIED

    bad, _ = status_transport(401, body=b"{}")
    refusing = _service(engine, settings, bad)
    refusing.probe_connection()

    check = refusing.describe().check
    assert check.state is VerificationState.PROVIDER_REFUSED
    assert check.probes_used == 2


def test_a_verified_verdict_drops_the_sentences_the_probe_made_false(
    engine: Engine, settings: Settings
) -> None:
    """The reasons list is pruned, not appended to.

    ``_NOT_VERIFIABLE_REASON`` opens with *anahtar dogrulanmadi* and was true
    of every state before ADR-0015. Leaving it beside a verified verdict would
    be a stale sentence next to a fresh one, which is the defect this round is
    about, printed in the same paragraph as its own correction.

    :data:`AUTH_HEADER_CAVEAT` is the opposite case and survives every state:
    the header works *and* the documentation still does not publish it, so the
    provider may still change it without a contract.
    """
    transport, _ = _accepting_transport()
    service = _connected(engine, settings, transport)

    before = service.describe().check.reasons
    after = service.probe_connection().check.reasons

    assert any("dogrulanmadi" in reason for reason in before)
    assert not any("dogrulanmadi" in reason for reason in after)
    assert AUTH_HEADER_CAVEAT in before
    assert AUTH_HEADER_CAVEAT in after
    # And the reasons stay plural: a single sentence reads like one fixable
    # problem, the list is the actual position.
    assert len(after) >= 2


def test_no_reason_anywhere_still_says_the_probe_is_unimplemented(
    engine: Engine, settings: Settings
) -> None:
    """``_NO_PROBE_REASON`` is gone from every state it used to appear in.

    It said the real request "henuz uygulanmamistir" - *has not been
    implemented yet* - which was the button's own confession, filed in a list
    most people never open.
    """
    transport, _ = _accepting_transport()
    service = _connected(engine, settings, transport)

    states = [service.describe().check, service.probe_connection().check]
    service.forget_credential()
    states.append(service.describe().check)

    for check in states:
        for reason in (*check.reasons, check.detail):
            assert "uygulanmamistir" not in reason, reason


# ---------------------------------------------------------------------------
# Refusals that cost nothing
# ---------------------------------------------------------------------------


def test_a_probe_without_a_credential_sends_nothing(
    engine: Engine, settings: Settings
) -> None:
    transport, recorder = never_called_transport()
    service = _service(engine, settings, transport)

    with pytest.raises(OpenCodeConfigurationError):
        service.probe_connection()

    assert recorder.count == 0


def test_a_probe_with_no_selected_model_is_refused_and_nothing_is_substituted(
    engine: Engine, settings: Settings
) -> None:
    """Station does not pick a model, least of all to spend money with one."""
    transport, recorder = never_called_transport()
    service = _connected(engine, settings, transport, model="")

    with pytest.raises(ModelNotSelectableError) as caught:
        service.probe_connection()

    assert "model secmez" in str(caught.value)
    assert recorder.count == 0


def test_a_model_outside_the_measured_family_is_refused_by_name(
    engine: Engine, settings: Settings
) -> None:
    """The probe body is ``chat/completions`` shaped because that shape was
    measured. A ``responses`` model is refused rather than sent to a contract
    nobody has read."""
    transport, recorder = never_called_transport()
    service = _connected(
        engine, settings, transport, model=SECOND_OBSERVED_MODEL_ID
    )

    with pytest.raises(ModelNotSelectableError) as caught:
        service.probe_connection()

    assert "protokol ailesi" in str(caught.value)
    assert recorder.count == 0


# ---------------------------------------------------------------------------
# The ceiling
# ---------------------------------------------------------------------------


def test_the_ceiling_stops_the_button_and_says_where_you_stand(
    engine: Engine, settings: Settings
) -> None:
    """Press past the ceiling: nothing leaves, and the reason is on screen.

    ADR-0013's shape, applied to this button. The counting side is the
    **transport recorder**, not the ledger: a test that only read the count
    back would pass against a build that spent the call and forgot to record
    it.
    """
    transport, recorder = _accepting_transport()
    service = _connected(engine, settings, transport)

    for _ in range(MAX_CONNECTION_PROBES):
        service.probe_connection()
    spent = recorder.count
    assert spent == MAX_CONNECTION_PROBES

    for _ in range(3):
        view = service.probe_connection()

    assert recorder.count == spent, "a press past the ceiling reached the provider"
    assert view.check.probes_used == MAX_CONNECTION_PROBES
    assert any(
        f"{MAX_CONNECTION_PROBES}/{MAX_CONNECTION_PROBES}" in reason
        for reason in view.check.reasons
    )


def test_forgetting_and_re_saving_the_same_key_does_not_hand_back_the_ceiling(
    engine: Engine, settings: Settings
) -> None:
    """The ``forget`` defect ADR-0013 named, closed before it could be opened.

    The ledger is keyed by the credential **fingerprint** and has no foreign
    key to the metadata row, so removing the credential does not remove the
    spend. Re-entering the same key lands on the same row.
    """
    transport, recorder = _accepting_transport()
    service = _connected(engine, settings, transport)
    for _ in range(MAX_CONNECTION_PROBES):
        service.probe_connection()

    service.forget_credential()
    service.store_credential(TEST_ONLY_OPENCODE_CREDENTIAL)
    service.probe_connection()

    assert recorder.count == MAX_CONNECTION_PROBES
    assert service.describe().check.probes_used == MAX_CONNECTION_PROBES


def test_the_ceiling_survives_a_restart_of_the_process(
    engine: Engine, settings: Settings
) -> None:
    """A second service against the same database is what a relaunch is."""
    transport, recorder = _accepting_transport()
    service = _connected(engine, settings, transport)
    for _ in range(MAX_CONNECTION_PROBES):
        service.probe_connection()

    relaunched = _service(engine, settings, transport)
    relaunched.probe_connection()

    assert recorder.count == MAX_CONNECTION_PROBES


def test_a_different_key_starts_with_its_own_ceiling(
    engine: Engine, settings: Settings
) -> None:
    """The recourse ADR-0013 3 asks for, and the reason it is not a reset.

    A different key is a different secret and a question nobody has asked yet,
    so it has its own budget - and reaching it costs the user the key, which is
    exactly what a reset button would not.
    """
    transport, recorder = _accepting_transport()
    service = _connected(engine, settings, transport)
    for _ in range(MAX_CONNECTION_PROBES):
        service.probe_connection()

    service.store_credential(SECOND_TEST_ONLY_CREDENTIAL)
    view = service.probe_connection()

    assert recorder.count == MAX_CONNECTION_PROBES + 1
    assert view.check.probes_used == 1
    assert view.check.state is VerificationState.VERIFIED


# ---------------------------------------------------------------------------
# The credential does not come back
# ---------------------------------------------------------------------------


def test_a_provider_that_echoes_the_credential_leaks_it_nowhere(
    engine: Engine, settings: Settings
) -> None:
    """The probe is the one operation that sends the key on purpose.

    So the canary is planted where an upstream would put it - inside the error
    body of the very request that carried it - and then looked for in every
    place this feature writes: the verdict a person reads, every reason beside
    it, the stored ledger row and the database file itself.

    The excerpt is computed inside the client's redaction window, which is why
    it comes back as ``<redacted>`` rather than as nothing: a diagnostic that
    shows nothing is a diagnostic somebody removes.
    """
    reflected = json.dumps(
        {
            "error": {
                "message": f"invalid key: {TEST_ONLY_OPENCODE_CREDENTIAL}",
                "type": "authentication_error",
            }
        }
    ).encode()
    transport, _ = status_transport(401, body=reflected)
    service = _connected(engine, settings, transport)

    view = service.probe_connection()

    assert view.check.state is VerificationState.PROVIDER_REFUSED
    assert "<redacted>" in view.check.detail
    for text in (view.check.detail, *view.check.reasons):
        assert TEST_ONLY_OPENCODE_CREDENTIAL not in text

    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT fingerprint, state, detail FROM opencode_probe_ledger"
        ).all()
    assert len(rows) == 1
    for row in rows:
        for value in row:
            assert TEST_ONLY_OPENCODE_CREDENTIAL not in str(value)

    engine.dispose()
    blob = settings.database_path.read_bytes()
    assert TEST_ONLY_OPENCODE_CREDENTIAL.encode() not in blob
    assert TEST_ONLY_OPENCODE_CREDENTIAL.lower().encode() not in blob
    assert TEST_ONLY_OPENCODE_CREDENTIAL.upper().encode() not in blob


# ---------------------------------------------------------------------------
# The counter has one writer, and the row has no deleter
# ---------------------------------------------------------------------------

_ATTRIBUTE = "probes_used"


class _CounterWriteFinder(ast.NodeVisitor):
    """Every write to ``probes_used``, with the function it happens in.

    ``test_model_planner.py``'s scanner, aimed at the second counter. It looks
    for the **attribute as an assignment target** rather than for the name, so
    the ORM declaration in ``db/models.py`` - a ``mapped_column`` binding - is
    not a write and needs no exemption.
    """

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.offenders: list[str] = []
        self._stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check(node.target)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "setattr":
            named = node.args[1] if len(node.args) > 1 else None
            if isinstance(named, ast.Constant) and named.value == _ATTRIBUTE:
                self._record()
        self.generic_visit(node)

    def _check(self, target: ast.expr) -> None:
        if isinstance(target, ast.Attribute) and target.attr == _ATTRIBUTE:
            self._record()

    def _record(self) -> None:
        where = self._stack[-1] if self._stack else "<module>"
        self.offenders.append(f"{self.filename}:{where}")


def _counter_writes(root: Path) -> list[str]:
    """Every write to the probe counter anywhere under ``station_api``."""
    writes: list[str] = []
    for path in sorted((root / "station_api").rglob("*.py")):
        finder = _CounterWriteFinder(path.name)
        finder.visit(ast.parse(path.read_text(encoding="utf-8")))
        writes.extend(finder.offenders)
    return sorted(writes)


def test_nothing_lowers_the_connection_probe_counter(api_source_root: Path) -> None:
    """One writer, and it adds. There is no reset in this product.

    The cost is real and is pinned here rather than hoped for: a credential
    whose probes are spent stays spent, because a reset is ``forget`` returning
    under another name (ADR-0013 3). A behavioural test can only say the paths
    that exist today do not lower it; this says none exists.
    """
    writes = _counter_writes(api_source_root)

    assert writes == [THE_ONLY_PROBE_COUNTER_WRITE], (
        "the connection-probe counter grew a second writer; it is what keeps a "
        f"metered button from being pressed without limit: {writes}"
    )


def test_the_probe_counter_scan_would_see_a_planted_reset(tmp_path: Path) -> None:
    """Guards the guard: a scan that found nothing would satisfy a one-element
    comparison the moment the real method is renamed."""
    planted = tmp_path / "station_api" / "planted"
    planted.mkdir(parents=True)
    (planted / "reset.py").write_text(
        "\n".join(
            (
                "def clear(row):",
                "    row.probes_used = 0",
                "def discount(row):",
                "    row.probes_used -= 1",
                "def sneak(row):",
                '    setattr(row, "probes_used", 0)',
            )
        ),
        encoding="utf-8",
    )

    assert _counter_writes(tmp_path) == [
        "reset.py:clear",
        "reset.py:discount",
        "reset.py:sneak",
    ]


def test_the_probe_ledger_row_is_never_deleted_and_reaches_only_two_modules(
    api_source_root: Path,
) -> None:
    """The other way to lower a count: remove the row that holds it.

    ADR-0013 5 found this by mutation on the first ledger - ``session.delete``
    lowers a count to zero without ever assigning to it - so the same two doors
    are closed here. Nothing anywhere names ``OpenCodeProbeLedger`` inside a
    delete, and the class is reachable from exactly two modules: the one that
    declares it and the one that counts with it. A third module able to read
    the table is a third module able to write it, whatever it does today.
    """
    naming: list[str] = []
    deleters: list[str] = []
    for path in sorted((api_source_root / "station_api").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = [
            node
            for node in ast.walk(tree)
            if (isinstance(node, ast.Name) and node.id == "OpenCodeProbeLedger")
            or (isinstance(node, ast.Attribute) and node.attr == "OpenCodeProbeLedger")
            or (isinstance(node, ast.alias) and node.name == "OpenCodeProbeLedger")
            or (isinstance(node, ast.ClassDef) and node.name == "OpenCodeProbeLedger")
        ]
        if not names:
            continue
        naming.append(
            str(path.relative_to(api_source_root / "station_api")).replace("\\", "/")
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Delete):
                deleters.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Call) and any(
                isinstance(argument, ast.Name)
                and argument.id == "OpenCodeProbeLedger"
                for argument in node.args
            ):
                function = node.func
                called = (
                    function.id
                    if isinstance(function, ast.Name)
                    else function.attr
                    if isinstance(function, ast.Attribute)
                    else ""
                )
                if called in ("delete", "Delete"):
                    deleters.append(f"{path.name}:{node.lineno}")

    assert deleters == [], f"the probe ledger grew a way to remove its rows: {deleters}"
    assert naming == ["db/models.py", "opencode/service.py"], naming


# ---------------------------------------------------------------------------
# The revision
# ---------------------------------------------------------------------------


def test_migration_0012_added_one_table_and_touched_nothing_else(
    engine: Engine,
) -> None:
    """Additive only, and shaped to be a per-credential ceiling.

    The shape is the argument: the fingerprint is the primary key, so the
    ceiling is per credential rather than per installation or per session, and
    there is **no foreign key** to ``opencode_credential_metadata`` - a cascade
    from that row is precisely the "forget hands back a ceiling" defect.
    """
    inspector = inspect(engine)
    names = set(inspector.get_table_names())

    for table in (
        "app_metadata",
        "identity",
        "task_record",
        "opencode_credential_metadata",
        "opencode_catalog_check",
        "opencode_model_snapshot",
        "model_call_ledger",
    ):
        assert table in names, f"{table} disappeared"
    assert "opencode_probe_ledger" in names

    columns = {
        column["name"]: column for column in inspector.get_columns("opencode_probe_ledger")
    }
    assert set(columns) == {
        "fingerprint",
        "probes_used",
        "first_probe_at",
        "last_probe_at",
        "state",
        "http_status",
        "detail",
    }
    assert columns["fingerprint"]["primary_key"] == 1
    assert inspector.get_foreign_keys("opencode_probe_ledger") == []


def test_the_probe_ledger_has_no_secret_shaped_column(engine: Engine) -> None:
    """The table that names a credential is where a key column would look
    natural and be catastrophic."""
    forbidden = (
        "seed",
        "private",
        "secret",
        "mnemonic",
        "passphrase",
        "password",
        "key",
        "token",
    )
    offenders = [
        column["name"]
        for column in inspect(engine).get_columns("opencode_probe_ledger")
        if any(fragment in str(column["name"]).lower() for fragment in forbidden)
    ]

    assert offenders == []


def test_every_probe_outcome_has_a_verdict_of_its_own() -> None:
    """Three outcomes, three states, and no two that collapse into one.

    A mapping with a duplicate on the right-hand side would make a refusal and
    an inconclusive answer wear the same badge, which is the reduction this
    whole round exists to remove.
    """
    from station_api.opencode.service import _STATE_FOR

    assert set(_STATE_FOR) == set(ProbeOutcome)
    assert len(set(_STATE_FOR.values())) == len(ProbeOutcome)
    assert VerificationState.SAVED_UNVERIFIED not in set(_STATE_FOR.values())
