"""The proof routes: what they expose, what they hand over, and what they refuse.

Four refusals matter more than the rest:

* **there is no route that writes the bundle to a path.** ``share`` answers
  with a ``Content-Disposition`` and the browser decides where the file goes.
  No request names a directory, a filename or a traversal segment, so path
  traversal, symlinks and overwrite prompts are absent from the feature rather
  than defended against (ADR-0009 3);
* **there is no route that sends anything anywhere.** ``public-share`` records
  that an archived send belongs to this task; it cannot cause one, and
  ``OUTBOUND_CLIENT_MODULES`` stays at five (ADR-0009 11);
* **there is no route that sets an evidence field to a value the caller
  chose.** ``acceptance`` writes ``user_acceptance`` after confirming the
  bundle is the one the person read, and ``public-share`` takes ``verified``
  from the archived record's own outcome;
* **accepting moves nothing.** ``ready_to_publish`` is derived from three
  separately verified fields and is not a side effect of a POST (SI-222,
  ADR-0009 8).

The ordinary guarantees are checked too - ``no-store``, CSRF on every
state-changing route, ``extra="forbid"`` on every body - because a new router
is exactly where a project stops inheriting them by accident.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from station_api.agent.service import AgentService
from station_api.agent.workspace import task_workspace, workspace_root
from station_api.compose.nonce import NonceReserver
from station_api.db.models import EvidenceRecord
from station_api.modules.registry import ModuleId
from station_api.proof.bundle import BUNDLE_FORMATS, BUNDLE_STEM
from station_api.proof.language import BUNDLE_SCOPE_SENTENCE, HASH_SCOPE_SENTENCE
from station_api.routes.proof import (
    ARTIFACT_BUNDLE_HEADER,
    ARTIFACT_DIGEST_HEADER,
    DELIVERED_AT_HEADER,
)
from station_api.schemas import EvidenceExportRequest, ProofShareRequest
from station_api.tasks.service import TaskService
from station_api.tasks.sources import TaskSourceId

from tests.security.agent_fixtures import plant_a_real_reparse_point, write_plan
from tests.security.conftest import collect_route_paths

pytestmark = pytest.mark.security

CSRF = "X-Station-CSRF"

PROOF_PREFIX = "/api/proof"

TEST_ONLY_DID = "did:key:zTESTONLYnotarealdidkeyvalue"
TEST_ONLY_ROOM = "mb-station-test-only"

#: Exactly the paths this router serves. Written out, so a route added later
#: is a change somebody reviews rather than a surface that grew.
EXPECTED_PATHS = {
    "/api/proof/{task_id}",
    "/api/proof/{task_id}/prepare",
    "/api/proof/{task_id}/share",
    "/api/proof/{task_id}/artifact",
    "/api/proof/{task_id}/acceptance",
    "/api/proof/{task_id}/public-share",
}


@pytest.fixture
def proof_task_id(app: FastAPI) -> str:
    """One task with a completed run, so a bundle has something in it."""
    tasks: TaskService = app.state.tasks
    agent: AgentService = app.state.agent
    view = tasks.open_task(
        module_id=ModuleId.AGENT_WORKSPACE,
        source=TaskSourceId.OPERATOR_REQUEST,
        content=b"TEST-ONLY http proof task",
        title="TEST-ONLY kanit gorevi",
    )
    agent.start_run(write_plan(agent, view.id))
    return view.id


def _archive_a_send(engine: Engine, *, outcome: str = "accepted") -> str:
    reserver = NonceReserver(engine)
    reservation = reserver.reserve(did=TEST_ONLY_DID, room=TEST_ONLY_ROOM)
    reserver.commit_to_send(reservation.id)

    evidence_id = uuid.uuid4().hex
    with Session(engine) as session, session.begin():
        session.add(
            EvidenceRecord(
                id=evidence_id,
                reservation_id=reservation.id,
                did=TEST_ONLY_DID,
                room=TEST_ONLY_ROOM,
                nonce=reservation.nonce,
                canonical="TEST-ONLY canonical",
                canonical_sha256="0" * 64,
                signature="TEST-ONLY-signature",
                signature_verified=True,
                request_body=b"TEST-ONLY request",
                request_sha256="1" * 64,
                response_body=b"TEST-ONLY response",
                response_sha256="2" * 64,
                http_status=200,
                write_outcome=outcome,
                recorded_at=datetime.now(UTC),
                external_anchor=None,
            )
        )
    return evidence_id


def _prepare(client: TestClient, csrf_token: str, task_id: str) -> dict[str, object]:
    response = client.post(
        f"{PROOF_PREFIX}/{task_id}/prepare", headers={CSRF: csrf_token}
    )
    assert response.status_code == 200, response.text
    payload: dict[str, object] = response.json()
    return payload


# ---------------------------------------------------------------------------
# The surface
# ---------------------------------------------------------------------------


def test_the_router_serves_exactly_these_paths(app: FastAPI) -> None:
    paths = {
        path for path in collect_route_paths(app) if path.startswith(PROOF_PREFIX)
    }

    assert paths == EXPECTED_PATHS


def test_no_proof_route_names_a_write_lane_a_path_or_a_command(
    app: FastAPI,
) -> None:
    """A known path is asserted first, so a blind walk fails rather than passes.

    ``collect_route_paths`` has gone blind once already in this repository -
    an included router with no ``path`` attribute produced a set of empty
    strings and every "no route contains X" assertion passed while inspecting
    nothing.
    """
    paths = collect_route_paths(app)

    assert f"{PROOF_PREFIX}/{{task_id}}" in paths
    for path in paths:
        if not path.startswith(PROOF_PREFIX):
            continue
        lowered = path.lower()
        for forbidden in ("say", "note", "exec", "shell", "file", "path", "download"):
            assert forbidden not in lowered, path


def test_every_proof_read_is_no_store(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    assert csrf_token
    response = client.get(f"{PROOF_PREFIX}/{proof_task_id}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.parametrize(
    ("suffix", "body"),
    [
        ("prepare", None),
        ("share", {"share_token": "x", "format": "json", "acknowledged": True}),
        (
            "artifact",
            {"share_token": "x", "name": "rapor.json", "acknowledged": True},
        ),
        ("acceptance", {"bundle_sha256": "0" * 64}),
        ("public-share", {"evidence_id": "0" * 32}),
    ],
)
def test_every_state_changing_route_requires_csrf(
    client: TestClient,
    csrf_token: str,
    proof_task_id: str,
    suffix: str,
    body: dict[str, object] | None,
) -> None:
    """Checked on every route rather than on one, because middleware is global
    until somebody adds a route that is not."""
    assert csrf_token
    response = client.post(f"{PROOF_PREFIX}/{proof_task_id}/{suffix}", json=body)

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("suffix", "body"),
    [
        ("share", {"share_token": "x", "format": "json", "acknowledged": True}),
        (
            "artifact",
            {"share_token": "x", "name": "rapor.json", "acknowledged": True},
        ),
        ("acceptance", {"bundle_sha256": "0" * 64}),
        ("public-share", {"evidence_id": "0" * 32}),
    ],
)
def test_every_request_model_forbids_extra_fields(
    client: TestClient,
    csrf_token: str,
    proof_task_id: str,
    suffix: str,
    body: dict[str, object],
) -> None:
    """``extra='forbid'`` on every body, so a stray key is a 422 not a shrug."""
    response = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/{suffix}",
        json={**body, "stray": "TEST-ONLY"},
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# What the read says
# ---------------------------------------------------------------------------


def test_the_read_names_every_gap_and_states_what_a_digest_proves(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    """ADR-0009 11 on the wire, beside the number it qualifies."""
    assert csrf_token
    payload = client.get(f"{PROOF_PREFIX}/{proof_task_id}").json()

    assert payload["hash_scope"] == HASH_SCOPE_SENTENCE
    assert payload["bundle_scope"] == BUNDLE_SCOPE_SENTENCE
    assert len(payload["artifact_set_sha256"]) == 64
    assert len(payload["bundle_sha256"]) == 64
    assert payload["missing"], "a task with no test result has a gap to name"
    for entry in payload["missing"]:
        assert entry["key"] and entry["detail"]
    assert list(payload["formats"]) == list(BUNDLE_FORMATS)


def test_the_two_unproduced_claims_are_reported_with_their_reasons(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    """ADR-0009 6 and 7 on the wire. Absent keys would read as an oversight."""
    assert csrf_token
    payload = client.get(f"{PROOF_PREFIX}/{proof_task_id}").json()
    claims = {entry["key"]: entry for entry in payload["claims"]}

    assert {"independent_check", "exit_code", "test_result"} <= set(claims)
    for claim in claims.values():
        assert claim["state"] == "not_implemented"
        assert claim["detail"].strip()


def test_the_response_carries_no_score_and_no_single_badge(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    """Four fields, named gaps, and nothing that sums them.

    The whole model exists to stop a reader being handed a conjunction they
    cannot take apart, so the body is checked for the shapes a summary takes.
    """
    assert csrf_token
    body = client.get(f"{PROOF_PREFIX}/{proof_task_id}").text.lower()

    for forbidden in ("score", "percent", "completeness", "grade", "rating", "badge"):
        assert forbidden not in body


def test_a_missing_task_is_a_404_rather_than_an_armoured_500(
    client: TestClient, csrf_token: str
) -> None:
    assert csrf_token
    response = client.get(f"{PROOF_PREFIX}/{'0' * 32}")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Prepare, then share
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bundle_format", ["json", "markdown"])
def test_a_prepared_bundle_is_delivered_as_a_download(
    client: TestClient, csrf_token: str, proof_task_id: str, bundle_format: str
) -> None:
    """The whole point of ADR-0009 3, end to end.

    A ``Content-Disposition`` with a sanitised constant stem, the format's own
    media type, and the moment of the copy in a header rather than in the
    body.
    """
    prepared = _prepare(client, csrf_token, proof_task_id)

    response = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/share",
        json={
            "share_token": prepared["share_token"],
            "format": bundle_format,
            "acknowledged": True,
        },
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="')
    assert BUNDLE_STEM in disposition
    assert ".." not in disposition and "/" not in disposition
    assert "\r" not in disposition and "\n" not in disposition
    assert response.headers["cache-control"] == "no-store"
    assert response.headers[DELIVERED_AT_HEADER]
    assert response.content


def test_a_share_without_the_acknowledgement_never_reaches_a_handler(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    """``acknowledged`` is ``Literal[True]`` with no default.

    A body that omits it, and a body that says ``false``, are both refused by
    the model before the route runs - the rule the evidence export is built
    on, applied to the surface that hands a proof to the browser.

    Since an adversarial review of H3 this is the **only** refusal of a missing
    acknowledgement on this route. The handler used to re-check the same field
    and call itself the second of two independent refusals; ``Literal[True]``
    admits one value, so that branch could never be taken and deleting it
    failed nothing. The branch is gone, and
    ``test_the_acknowledgement_is_enforced_by_the_annotation_and_only_there``
    below pins the annotation that replaced it.
    """
    prepared = _prepare(client, csrf_token, proof_task_id)

    for body in (
        {"share_token": prepared["share_token"], "format": "json"},
        {
            "share_token": prepared["share_token"],
            "format": "json",
            "acknowledged": False,
        },
    ):
        response = client.post(
            f"{PROOF_PREFIX}/{proof_task_id}/share",
            json=body,
            headers={CSRF: csrf_token},
        )
        assert response.status_code == 422


def test_a_reparse_point_in_the_workspace_is_a_stated_refusal_not_a_500(
    client: TestClient,
    app: FastAPI,
    csrf_token: str,
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real junction, and the answer a person gets because of it.

    Measured on H3 before this was fixed: ``mklink /J`` inside
    ``workspace/v1/<task_id>`` made ``GET /api/proof/{id}`` answer **500**.
    ``AgentService.workspace_files`` raised ``WorkspaceError`` from the
    reparse walk, ``ProofService.build`` passed it through, and every proof
    route catches ``(ProofError, TaskError)`` only. The generic contract
    redacted the body, so nothing leaked - what was lost was the sentence. The
    workspace layer knew precisely what was wrong and the route replaced that
    with "an error occurred", on a screen whose whole subject is telling a
    person what this machine can and cannot establish.

    ``proof.build`` now translates ``AgentError``, so the refusal arrives with
    its own status and its own wording.

    Driven against an actual reparse point, with the predicate forced on the
    same real path where the platform will not plant one - no skip, because a
    guard that has only ever been monkeypatched is the guard this repository
    keeps finding holes in.
    """
    assert csrf_token  # the session these reads need; no body is posted
    tasks: TaskService = app.state.tasks
    view = tasks.open_task(
        module_id=ModuleId.AGENT_WORKSPACE,
        source=TaskSourceId.OPERATOR_REQUEST,
        content=b"TEST-ONLY reparse proof task",
        title="TEST-ONLY junction gorevi",
    )

    elsewhere = data_dir / "baska-taraf"
    elsewhere.mkdir(parents=True, exist_ok=True)
    (elsewhere / "rapor.md").write_text("TEST-ONLY disarida", encoding="utf-8")

    workspace_root(data_dir).mkdir(parents=True, exist_ok=True)
    planted = task_workspace(data_dir, view.id)

    # The permitted case first: with no reparse point the read answers 200, so
    # a route that refused everything would fail here rather than below.
    assert client.get(f"{PROOF_PREFIX}/{view.id}").status_code == 200

    real = plant_a_real_reparse_point(planted, elsewhere)
    if not real:  # pragma: no cover - only where the platform plants neither
        planted.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            os.path, "isjunction", lambda path: Path(path) == planted
        )

    try:
        response = client.get(f"{PROOF_PREFIX}/{view.id}")

        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert "baglanti" in detail
        # The refusal is the workspace layer's own sentence, not a generic
        # one, and it names neither the planted path nor the other side.
        assert str(planted) not in detail
        assert str(elsewhere) not in detail

        # The run listing inherits nothing broken: ``routes/agent.py`` catches
        # ``AgentError``, and ``WorkspaceError`` is one, so that route already
        # answered a stated refusal. Asserted rather than assumed, because the
        # review that found the proof route reported this one as sharing the
        # defect and it does not.
        runs = client.get(f"/api/tasks/{view.id}/runs")
        assert runs.status_code == 400, runs.text
        assert "baglanti" in runs.json()["detail"]
    finally:
        if real:
            planted.rmdir()


def test_the_acknowledgement_is_enforced_by_the_annotation_and_only_there() -> None:
    """The annotation, pinned - because nothing else refuses now.

    ``ProofShareRequest.acknowledged`` is ``Literal[True]`` and has no
    default. Both halves matter and neither is visible from an HTTP response:
    widening the type to ``bool`` would make ``acknowledged: false`` reach a
    handler that no longer re-checks it, and giving it a default would let a
    body omit it entirely. The 422s above would keep passing through the first
    of those two changes, because a *missing* field is still a 422 under
    ``bool`` with no default - which is exactly how a defence disappears
    without a red test.

    Read off the model rather than off the source text, so a re-spelling that
    keeps the meaning passes and a widening that keeps the spelling does not.
    """
    field = ProofShareRequest.model_fields["acknowledged"]

    assert field.annotation == Literal[True]
    assert field.is_required()

    # And the twin that is *not* this shape, named here so the difference is a
    # measurement rather than a memory: the evidence export takes a plain bool
    # and its handler really does check it (``routes/evidence.py``).
    assert EvidenceExportRequest.model_fields["acknowledged"].annotation is bool


def test_a_format_outside_the_closed_set_is_a_422(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    prepared = _prepare(client, csrf_token, proof_task_id)

    response = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/share",
        json={
            "share_token": prepared["share_token"],
            "format": "zip",
            "acknowledged": True,
        },
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 422


def test_a_share_token_is_spent_once_over_http(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    """The single-use property, at the surface a client actually uses."""
    prepared = _prepare(client, csrf_token, proof_task_id)
    body = {
        "share_token": prepared["share_token"],
        "format": "json",
        "acknowledged": True,
    }

    first = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/share", json=body, headers={CSRF: csrf_token}
    )
    second = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/share", json=body, headers={CSRF: csrf_token}
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_an_unprepared_share_is_refused(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    """There is no way to take the file without first being shown it."""
    response = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/share",
        json={
            "share_token": "TEST-ONLY-not-a-token",
            "format": "json",
            "acknowledged": True,
        },
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Acceptance and the fourth field
# ---------------------------------------------------------------------------


def test_an_acceptance_records_the_field_and_leaves_the_state_alone(
    client: TestClient, csrf_token: str, app: FastAPI, proof_task_id: str
) -> None:
    """SI-222 at the HTTP surface: the input, not the output."""
    tasks: TaskService = app.state.tasks
    before = tasks.get(proof_task_id).state
    read = client.get(f"{PROOF_PREFIX}/{proof_task_id}").json()

    response = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/acceptance",
        json={"bundle_sha256": read["bundle_sha256"], "detail": "TEST-ONLY kabul"},
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 200
    payload = response.json()
    acceptance = next(
        row
        for row in payload["task"]["evidence_fields"]
        if row["evidence_field"] == "user_acceptance"
    )
    assert acceptance["state"] == "passed"
    assert payload["task"]["state"] == before.value
    assert tasks.get(proof_task_id).state is before


def test_an_acceptance_for_a_stale_bundle_is_a_conflict(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    response = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/acceptance",
        json={"bundle_sha256": "0" * 64},
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 409


def test_the_fourth_field_is_marked_only_from_an_archived_send(
    client: TestClient, csrf_token: str, app: FastAPI, proof_task_id: str
) -> None:
    """ADR-0009 1 at the surface: an id with no row is a 404, a real one passes."""
    missing = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/public-share",
        json={"evidence_id": "0" * 32},
        headers={CSRF: csrf_token},
    )
    assert missing.status_code == 404

    evidence_id = _archive_a_send(app.state.engine)
    accepted = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/public-share",
        json={"evidence_id": evidence_id},
        headers={CSRF: csrf_token},
    )

    assert accepted.status_code == 200
    share = next(
        row
        for row in accepted.json()["task"]["evidence_fields"]
        if row["evidence_field"] == "public_share"
    )
    assert share["state"] == "passed"
    assert share["ref_id"] == evidence_id


def test_a_public_share_body_carries_no_address_and_no_text(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    """The route cannot be turned into a send by anything in its body.

    An evidence-record identity and an optional note, and nothing else: no
    room, no URL, no message. A key that looked like a destination is a 422,
    which is what keeps "this route records a send that already happened" true
    of the model rather than only of the handler.
    """
    for stray in ("room", "url", "text", "did", "host"):
        response = client.post(
            f"{PROOF_PREFIX}/{proof_task_id}/public-share",
            json={"evidence_id": "0" * 32, stray: "TEST-ONLY"},
            headers={CSRF: csrf_token},
        )
        assert response.status_code == 422, stray


def test_the_task_reports_the_fourth_field_as_available_now(
    client: TestClient, csrf_token: str, proof_task_id: str
) -> None:
    """The wire value moved with the fact.

    ``public_share_available`` was ``Literal[False]`` until H3. It is a plain
    boolean now and it is ``true``, which is the honest answer: the field can
    be filled - from an archived send and from nothing else.

    This test reads the *value* over HTTP and says nothing about where it came
    from: a hard-coded ``True`` on the model passes it, which an adversarial
    review measured. The claim that the wire is derived from
    ``UNFILLABLE_FIELDS`` is driven in ``test_task_evidence.py``'s
    ``test_the_task_status_view_still_reports_a_closed_field_as_unavailable``,
    which closes the field and re-reads the projection. The docstring is
    corrected rather than the assertion strengthened, because an HTTP test
    cannot reach the constant that decides it.
    """
    assert csrf_token
    payload = client.get(f"{PROOF_PREFIX}/{proof_task_id}").json()

    assert payload["task"]["public_share_available"] is True
    assert payload["task"]["public_share_detail"].strip()
    # And it still does not gate finishing.
    assert "public_share" not in payload["task"]["blocking_fields"]


# ---------------------------------------------------------------------------
# Taking the file itself
# ---------------------------------------------------------------------------
#
# The bundle is the document *about* a task. This is the report the run wrote.
# An independent review measured that the second one could not be taken at all:
# a download contained the artifact's name and digest and not its contents.

#: A marker a substring search can find in a response body.
TEST_ONLY_BODY_MARKER = "TEST-ONLY-http-artifact-body-4c71"

#: 64 hex characters. The canary shape ``secret_scan`` refuses; never a key.
TEST_ONLY_HTTP_CANARY = "f0e1d2c3" * 8


def _run_producing(app: FastAPI, task_id: str, *, name: str, body: str) -> None:
    agent: AgentService = app.state.agent
    agent.start_run(
        write_plan(agent, task_id, name=name, body=body, expected=(name,))
    )


def _artifact_task(app: FastAPI, *, name: str, body: str) -> str:
    tasks: TaskService = app.state.tasks
    view = tasks.open_task(
        module_id=ModuleId.AGENT_WORKSPACE,
        source=TaskSourceId.OPERATOR_REQUEST,
        content=b"TEST-ONLY http artifact task",
        title="TEST-ONLY cikti gorevi",
    )
    _run_producing(app, view.id, name=name, body=body)
    return view.id


def _take_artifact(
    client: TestClient, csrf_token: str, task_id: str, name: str
):  # type: ignore[no-untyped-def]
    prepared = _prepare(client, csrf_token, task_id)
    return client.post(
        f"{PROOF_PREFIX}/{task_id}/artifact",
        json={
            "share_token": prepared["share_token"],
            "name": name,
            "acknowledged": True,
        },
        headers={CSRF: csrf_token},
    )


def test_the_downloaded_bundle_carries_the_produced_file_over_http(
    client: TestClient, csrf_token: str, app: FastAPI
) -> None:
    """The measured defect, at the surface a person actually uses.

    Asserted through the HTTP route rather than against the builder, because
    the measurement that found this was taken on a download: what reached the
    browser was an inventory. Both formats, since a person takes one of them.
    """
    body = f'{{"TEST_ONLY": "{TEST_ONLY_BODY_MARKER}"}}'
    task_id = _artifact_task(app, name="rapor.json", body=body)

    for bundle_format in BUNDLE_FORMATS:
        prepared = _prepare(client, csrf_token, task_id)
        response = client.post(
            f"{PROOF_PREFIX}/{task_id}/share",
            json={
                "share_token": prepared["share_token"],
                "format": bundle_format,
                "acknowledged": True,
            },
            headers={CSRF: csrf_token},
        )
        assert response.status_code == 200, response.text
        assert TEST_ONLY_BODY_MARKER in response.text, bundle_format


def test_one_produced_file_is_handed_over_as_that_file(
    client: TestClient, csrf_token: str, app: FastAPI
) -> None:
    """The response body **is** the artifact, with nothing wrapped around it.

    Not JSON with the text inside a field: a person saves this response and
    hashes it, and the number they get has to be the number the bundle printed.
    Any envelope at all would break that, which is why the digest travels in a
    header instead.
    """
    body = f'{{"TEST_ONLY": "{TEST_ONLY_BODY_MARKER}"}}'
    task_id = _artifact_task(app, name="rapor.json", body=body)

    response = _take_artifact(client, csrf_token, task_id, "rapor.json")

    assert response.status_code == 200, response.text
    assert response.content == body.encode("utf-8")
    assert response.headers[ARTIFACT_DIGEST_HEADER] == hashlib.sha256(
        body.encode("utf-8")
    ).hexdigest()
    assert len(response.headers[ARTIFACT_BUNDLE_HEADER]) == 64
    assert response.headers[DELIVERED_AT_HEADER]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="rapor.json"'
    )


def test_an_artifact_is_never_served_as_markup(
    client: TestClient, csrf_token: str, app: FastAPI
) -> None:
    """The one that would be a same-origin scripting hole.

    A workspace name only has to survive ``[A-Za-z0-9._-]``, so ``rapor.html``
    is a legal artifact and a run can write one. Station serves its own SPA
    from this origin and has no CORS middleware by design, so a response that
    let a browser render that file would put markup this product did not write
    on this product's origin, with this session's cookie. The media type is
    fixed, the disposition is ``attachment``, and ``nosniff`` closes the third
    door.
    """
    body = "<script>TEST_ONLY=1</script>"
    task_id = _artifact_task(app, name="rapor.html", body=body)

    response = _take_artifact(client, csrf_token, task_id, "rapor.html")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == body.encode("utf-8")


def test_an_artifact_delivery_spends_the_approval_exactly_once(
    client: TestClient, csrf_token: str, app: FastAPI
) -> None:
    """One approval, one file. The bundle route's rule, not a looser one.

    The two download routes share the same spending path on purpose: an
    artifact leaving this machine and a bundle leaving this machine are the
    same event with different bytes, and a second route that spent tokens more
    generously would be the quietest way to lose the property.
    """
    task_id = _artifact_task(app, name="rapor.json", body='{"TEST_ONLY": true}')
    prepared = _prepare(client, csrf_token, task_id)
    payload = {
        "share_token": prepared["share_token"],
        "name": "rapor.json",
        "acknowledged": True,
    }

    first = client.post(
        f"{PROOF_PREFIX}/{task_id}/artifact", json=payload, headers={CSRF: csrf_token}
    )
    second = client.post(
        f"{PROOF_PREFIX}/{task_id}/artifact", json=payload, headers={CSRF: csrf_token}
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 409


def test_a_refused_artifact_delivery_still_spends_the_token(
    client: TestClient, csrf_token: str, app: FastAPI
) -> None:
    """A refusal is a use. Asking for a file that is not there burns the
    approval, so a token cannot be probed name by name until one lands."""
    task_id = _artifact_task(app, name="rapor.json", body='{"TEST_ONLY": true}')
    prepared = _prepare(client, csrf_token, task_id)

    missing = client.post(
        f"{PROOF_PREFIX}/{task_id}/artifact",
        json={
            "share_token": prepared["share_token"],
            "name": "yok.json",
            "acknowledged": True,
        },
        headers={CSRF: csrf_token},
    )
    retry = client.post(
        f"{PROOF_PREFIX}/{task_id}/artifact",
        json={
            "share_token": prepared["share_token"],
            "name": "rapor.json",
            "acknowledged": True,
        },
        headers={CSRF: csrf_token},
    )

    assert missing.status_code == 404
    assert retry.status_code == 409


@pytest.mark.parametrize(
    "name",
    ["../rapor.json", "..\\rapor.json", "C:rapor.json", "alt/rapor.json", ""],
)
def test_a_name_carrying_path_syntax_never_reaches_a_handler(
    client: TestClient, csrf_token: str, proof_task_id: str, name: str
) -> None:
    """Depth, not the defence.

    The name never reaches the filesystem - it selects an entry from a document
    built from the workspace listing - so none of these could traverse anything
    even if they arrived. They are refused at the schema anyway, because a
    request that *contains* a traversal is a request nobody should have to
    reason about twice.
    """
    prepared = _prepare(client, csrf_token, proof_task_id)
    response = client.post(
        f"{PROOF_PREFIX}/{proof_task_id}/artifact",
        json={
            "share_token": prepared["share_token"],
            "name": name,
            "acknowledged": True,
        },
        headers={CSRF: csrf_token},
    )

    assert response.status_code == 422


def test_an_artifact_whose_body_was_left_out_is_a_stated_refusal(
    client: TestClient, csrf_token: str, app: FastAPI
) -> None:
    """A canary in a produced file, refused at the download rather than served.

    The secret scan excludes the body from the bundle; this asserts the second
    half - that the separate download cannot be used to walk around the
    exclusion. The refusal carries the sentence that says why, and never the
    value that caused it.
    """
    task_id = _artifact_task(
        app, name="rapor.json", body=f'{{"TEST_ONLY_canary": "{TEST_ONLY_HTTP_CANARY}"}}'
    )

    response = _take_artifact(client, csrf_token, task_id, "rapor.json")

    assert response.status_code == 409
    assert TEST_ONLY_HTTP_CANARY not in response.text
    assert "govdesi pakete alinmadi" in response.json()["detail"]


def test_an_artifact_from_another_task_is_not_reachable_with_this_approval(
    client: TestClient, csrf_token: str, app: FastAPI
) -> None:
    """The approval is bound to a task, and the name is scoped by it.

    Two tasks, each with a file of the same name and different contents. An
    approval minted for one cannot be spent against the other, and the name
    resolves inside the bundle it was minted for rather than against a
    directory.
    """
    first = _artifact_task(app, name="rapor.json", body='{"TEST_ONLY": "first"}')
    second = _artifact_task(app, name="rapor.json", body='{"TEST_ONLY": "second"}')
    prepared = _prepare(client, csrf_token, first)

    crossed = client.post(
        f"{PROOF_PREFIX}/{second}/artifact",
        json={
            "share_token": prepared["share_token"],
            "name": "rapor.json",
            "acknowledged": True,
        },
        headers={CSRF: csrf_token},
    )

    assert crossed.status_code == 409
    # The *sentence* is asserted, not only the code. Without the task binding
    # the request would still be refused - the second task's bundle hashes
    # differently, so the digest comparison catches it - and a test that read
    # only the status could not tell the two refusals apart. Measured: deleting
    # the task check left this test green until this line was added.
    assert crossed.json()["detail"] == "Bu onay baska bir goreve ait."
    assert _take_artifact(client, csrf_token, second, "rapor.json").json() == {
        "TEST_ONLY": "second"
    }


def test_the_plain_read_still_hands_over_no_body(
    client: TestClient, csrf_token: str, app: FastAPI
) -> None:
    """The one route with no approval in front of it stays an inventory.

    ``GET /api/proof/{task_id}`` is a read: no acknowledgement, no single-use
    token, nothing spent. The bodies are inside the document it builds now, so
    the projection onto the wire is the only thing keeping them off this
    response - and a projection is exactly the kind of thing a later edit
    widens with ``**entry``.

    What the read does carry is the *absence*: a body left out is named in
    ``missing`` like every other gap, so a person can see what will not be in
    their download before they ask for it.
    """
    body = f'{{"TEST_ONLY": "{TEST_ONLY_BODY_MARKER}"}}'
    task_id = _artifact_task(app, name="rapor.json", body=body)

    response = client.get(f"{PROOF_PREFIX}/{task_id}", headers={CSRF: csrf_token})

    assert response.status_code == 200, response.text
    assert TEST_ONLY_BODY_MARKER not in response.text
    payload = response.json()
    assert [item["name"] for item in payload["artifacts"]] == ["rapor.json"]
    assert all("content" not in item for item in payload["artifacts"])


def test_the_read_names_a_body_it_could_not_carry(
    client: TestClient, csrf_token: str, app: FastAPI
) -> None:
    """An exclusion reaches the screen through the gap list that already exists.

    Reusing ``missing`` rather than adding a field to the artifact row is the
    point: this product already has one place where every absence is named,
    and a second one would be a second thing to remember to read.
    """
    task_id = _artifact_task(
        app,
        name="rapor.json",
        body=f'{{"TEST_ONLY_canary": "{TEST_ONLY_HTTP_CANARY}"}}',
    )

    response = client.get(f"{PROOF_PREFIX}/{task_id}", headers={CSRF: csrf_token})
    keys = {item["key"] for item in response.json()["missing"]}

    assert "artifact_body.rapor.json" in keys
    assert TEST_ONLY_HTTP_CANARY not in response.text
