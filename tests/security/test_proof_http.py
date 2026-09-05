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

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from station_api.agent.service import AgentService
from station_api.compose.nonce import NonceReserver
from station_api.db.models import EvidenceRecord
from station_api.modules.registry import ModuleId
from station_api.proof.bundle import BUNDLE_FORMATS, BUNDLE_STEM
from station_api.proof.language import BUNDLE_SCOPE_SENTENCE, HASH_SCOPE_SENTENCE
from station_api.routes.proof import DELIVERED_AT_HEADER
from station_api.tasks.service import TaskService
from station_api.tasks.sources import TaskSourceId

from tests.security.agent_fixtures import write_plan
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
    """The wire value moved with the fact, and is derived from the constant.

    ``public_share_available`` was ``Literal[False]`` until H3. It is a plain
    boolean now and it is ``true``, which is the honest answer: the field can
    be filled - from an archived send and from nothing else.
    """
    assert csrf_token
    payload = client.get(f"{PROOF_PREFIX}/{proof_task_id}").json()

    assert payload["task"]["public_share_available"] is True
    assert payload["task"]["public_share_detail"].strip()
    # And it still does not gate finishing.
    assert "public_share" not in payload["task"]["blocking_fields"]
