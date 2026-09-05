"""SI-272, SI-277, SI-281 - the scan HTTP surface, the state machine, and Kibble.

Three claims carry this file:

* **launching contacts nobody, and reading the surface contacts nobody.** The
  attempts are counted rather than asserted, which is the only way to know
  rather than to believe (Package F's rule for exactly this claim).
* **the scope is the room set in the body.** There is no route that walks the
  room universe, and a room the policy refuses is refused here too.
* **a scanned candidate is not an operator request.** It carries a different
  source, therefore a different ``source_version_id``, and it is born in a
  different state - two independent layers, so a view cannot collapse them by
  forgetting to read a column.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.config import Settings
from station_api.modules.registry import ModuleId
from station_api.tasks.service import TaskError, TaskService
from station_api.tasks.sources import SCAN_SOURCES, TaskSourceId, source_version_id
from station_api.tasks.states import INITIAL_STATE, PRODUCIBLE_STATES, TaskState
from station_api.workscan.candidates import candidate_id
from station_api.workscan.client import RoomScanClient
from station_api.workscan.errors import CandidateError, WorkScanError
from station_api.workscan.kibble import (
    ADAPTERS,
    SCORE_SELF_DESCRIPTION,
    SELF_DESCRIPTION,
    TABLE_PROVENANCE,
    AdapterSupport,
    VerificationState,
    get_adapter,
)
from station_api.workscan.language import (
    DERIVATION_HONESTY_SENTENCE,
    PROHIBITION_HONESTY_SENTENCE,
)
from station_api.workscan.service import (
    MAX_ROOMS_PER_SCAN,
    ScanResult,
    WorkScanService,
)

from tests.conftest import TEST_PORT
from tests.security.conftest import collect_route_paths, establish_session
from tests.security.workscan_fixtures import (
    DEFECT_LINE,
    HELP_LINE,
    MARKERS,
    QUIET_LINE,
    ROOM,
    SECOND_ROOM,
    WALLET_LINE,
    index_document,
    message,
    never_called_transport,
    room_document,
    routing_transport,
)

pytestmark = pytest.mark.security

STATUS_PATH = "/api/workscan/status"
ROOMS_PATH = "/api/workscan/rooms/refresh"
SCAN_PATH = "/api/workscan/scan"
SUGGEST_PATH = "/api/workscan/suggest"

STATE_CHANGING = (ROOMS_PATH, SCAN_PATH, SUGGEST_PATH)


def _documents() -> dict[str, dict[str, object]]:
    return {
        "/rooms": index_document(),
        f"/r/{ROOM}": room_document(
            messages=[
                message(1, HELP_LINE),
                message(2, WALLET_LINE),
                message(3, QUIET_LINE),
            ]
        ),
        f"/r/{SECOND_ROOM}": room_document(
            room=SECOND_ROOM, messages=[message(9, DEFECT_LINE)]
        ),
    }


def _service(engine: Engine, documents: dict[str, dict[str, object]] | None = None):  # type: ignore[no-untyped-def]
    transport, recorder = routing_transport(documents or _documents())  # type: ignore[arg-type]
    service = WorkScanService(
        client=RoomScanClient(transport=transport, sleep=lambda _: None),
        tasks=TaskService(engine=engine),
    )
    return service, recorder


@pytest.fixture
def mocked_app(settings: Settings, engine: Engine) -> FastAPI:
    """The application with a mock transport behind the scan.

    The same seam the composer's ``write_client`` and the OpenCode service
    are, and it widens nothing: the address still comes from the closed scan
    registry and is re-checked against the origin allow-list.
    """
    service, _ = _service(engine)
    application = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        workscan=service,
    )
    return application


@pytest.fixture
def mocked_client(mocked_app: FastAPI, base_url: str):  # type: ignore[no-untyped-def]
    with TestClient(mocked_app, base_url=base_url) as client:
        yield client


def _with_markers(application: FastAPI) -> None:
    """Give the app a room-class convention, the way a live check would.

    The status object is a frozen dataclass, so the whole object is replaced
    rather than mutated - which is what the real check does too. Reaching into
    the service's private state is the cheapest honest seam here: the
    alternative is running a full manifest check through a second mock
    transport, which would test the check rather than the scan.
    """
    from dataclasses import replace

    service = application.state.technocore
    service._state.status = replace(
        service.status(), room_class_markers=tuple(sorted(MARKERS))
    )


# ---------------------------------------------------------------------------
# Zero outbound, counted
# ---------------------------------------------------------------------------


def test_building_the_application_makes_no_outbound_request(
    settings: Settings, engine: Engine
) -> None:
    """Counted, not asserted. A launch that reads public rooms on its own is
    a crawler, not a product (ADR-0007 4)."""
    transport, recorder = never_called_transport()
    service = WorkScanService(
        client=RoomScanClient(transport=transport, sleep=lambda _: None),
        tasks=TaskService(engine=engine),
    )

    create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        workscan=service,
    )

    assert recorder.count == 0


def test_reading_the_status_makes_no_outbound_request(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    transport, recorder = never_called_transport()
    service = WorkScanService(
        client=RoomScanClient(transport=transport, sleep=lambda _: None),
        tasks=TaskService(engine=engine),
    )
    application = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        workscan=service,
    )

    with TestClient(application, base_url=base_url) as client:
        establish_session(client, application)
        for _ in range(3):
            assert client.get(STATUS_PATH).status_code == 200

    assert recorder.count == 0


def test_the_status_document_carries_the_honesty_sentence_and_the_polling_statement(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """ADR-0007 2: the cost of pattern matching is shown on every read."""
    establish_session(mocked_client, mocked_app)

    body = mocked_client.get(STATUS_PATH).json()

    assert "kalip eslesmesiyle" in body["honesty"]
    assert "her firsat gorulmez" in body["honesty"]
    assert "zamanlayici" in body["polling_statement"]
    assert sorted(body["never_sent_params"]) == ["n", "wait"]


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------


def test_the_surface_offers_exactly_four_routes_and_no_scan_everything_lane(
    mocked_app: FastAPI,
) -> None:
    paths = {
        path for path in collect_route_paths(mocked_app) if path.startswith("/api/workscan")
    }

    assert paths == {STATUS_PATH, ROOMS_PATH, SCAN_PATH, SUGGEST_PATH}
    assert "/api/workscan/scan/all" not in paths
    assert "/api/workscan/watch" not in paths


@pytest.mark.parametrize("path", STATE_CHANGING)
def test_a_state_changing_route_needs_a_csrf_value(
    mocked_client: TestClient, mocked_app: FastAPI, path: str
) -> None:
    establish_session(mocked_client, mocked_app)

    assert mocked_client.post(path, json={}).status_code == 403


def test_a_scan_without_a_verified_room_convention_is_refused(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """Fail-closed: no manifest check, no resolved room."""
    csrf = establish_session(mocked_client, mocked_app)

    reply = mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    )

    assert reply.status_code == 409
    assert "manifest" in reply.json()["detail"]


def test_a_scan_reads_only_the_rooms_in_the_body(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """The scope is the user's chosen set; the room universe is never walked."""
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)

    body = mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    ).json()

    assert body["last_scan"]["rooms"] == [ROOM]
    assert [result["room"] for result in body["last_scan"]["results"]] == [ROOM]


def test_the_lobby_is_refused_on_the_scan_route_too(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """INV-05 and ADR-0007 11, at the surface a user can actually reach."""
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)

    body = mocked_client.post(
        SCAN_PATH, json={"rooms": ["lobby"]}, headers={"X-Station-CSRF": csrf}
    ).json()

    assert body["last_scan"]["rooms"] == []
    failures = body["last_scan"]["failures"]
    assert len(failures) == 1
    assert failures[0]["room"] == "lobby"
    assert failures[0]["reason"] == "room_refused"


def test_a_room_that_cannot_be_read_is_named_rather_than_reported_as_empty(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """The distinction that matters most: "found nothing" is not "could not read"."""
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)

    body = mocked_client.post(
        SCAN_PATH,
        json={"rooms": [ROOM, "test-only-missing"]},
        headers={"X-Station-CSRF": csrf},
    ).json()

    assert body["last_scan"]["rooms"] == [ROOM]
    failures = {failure["room"]: failure for failure in body["last_scan"]["failures"]}
    assert failures["test-only-missing"]["reason"] == "room_unreadable"
    # And the room that did answer still produced its candidate.
    assert body["last_scan"]["candidate_count"] == 1


def test_a_refused_line_is_reported_in_the_response(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)

    body = mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    ).json()

    assert body["last_scan"]["refusal_count"] == 1
    refusal = body["last_scan"]["results"][0]["refusals"][0]
    assert refusal["shape"] == "wallet_or_payment"
    assert refusal["detail"].strip()
    # Three lines were read to produce one candidate and one refusal.
    assert body["last_scan"]["results"][0]["lines_read"] == 3


def test_the_scan_body_is_bounded_so_the_route_cannot_become_a_crawl(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)

    reply = mocked_client.post(
        SCAN_PATH,
        json={"rooms": [f"test-only-{index}" for index in range(MAX_ROOMS_PER_SCAN + 5)]},
        headers={"X-Station-CSRF": csrf},
    )

    assert reply.status_code == 422


def test_the_room_overview_carries_both_caller_written_caveats(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    csrf = establish_session(mocked_client, mocked_app)

    body = mocked_client.post(
        ROOMS_PATH, json={"limit": 50}, headers={"X-Station-CSRF": csrf}
    ).json()

    index = body["room_index"]
    assert index["room_name_caveat"].strip()
    assert "kv/topic" in index["topic_caveat"]
    assert index["staleness"]["declared_cache_seconds"] == 3
    assert all(room["authority"] == 3 for room in index["rooms"])


def test_a_candidate_in_the_response_carries_all_eight_elements(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)

    body = mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    ).json()
    candidate = body["last_scan"]["results"][0]["candidates"][0]

    assert candidate["source"]["room"] == ROOM
    assert candidate["source"]["seq"] == 1
    assert candidate["source"]["quote"]
    assert candidate["source"]["authority"] == 3
    assert candidate["benefit"] and candidate["deliverable"]
    assert candidate["success_condition"] and candidate["test_method"]
    assert candidate["capability"]["detail"]
    assert candidate["effort"]["label"] == "tahmin"
    assert candidate["budget_state"] == "not_implemented"
    assert candidate["permissions"] and candidate["risks"]
    assert "kapanis isareti gorulmedi" in candidate["open_state"]["detail"]


def test_no_response_field_reports_a_work_item_as_open(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """ADR-0007 8: no boolean, and no wording that would read as one."""
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)

    body = mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    ).json()
    candidate = body["last_scan"]["results"][0]["candidates"][0]

    assert "is_open" not in candidate
    assert "is_open" not in candidate["open_state"]
    assert set(candidate["open_state"]) == {"read_at", "detail"}


# ---------------------------------------------------------------------------
# Kibble: recorded, never contacted
# ---------------------------------------------------------------------------


def test_the_kibble_record_is_open_and_carries_both_columns(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    establish_session(mocked_client, mocked_app)

    adapters = mocked_client.get(STATUS_PATH).json()["adapters"]

    assert len(adapters) == 1
    record = adapters[0]
    assert record["id"] == "kibble"
    assert record["support"] == AdapterSupport.SUPPORT_UNVERIFIED.value
    assert record["adapter_written"] is False
    assert record["contacted"] is False
    assert record["authority"] == 3
    assert len(record["verified"]) >= 4
    assert len(record["unverified"]) >= 5
    assert all(fact["state"] == "verified" for fact in record["verified"])
    assert all(fact["state"] == "not_verified" for fact in record["unverified"])
    assert record["provenance"] == TABLE_PROVENANCE
    assert "2026-09-04" in record["provenance"]


def test_the_services_own_disclaimer_is_carried_verbatim() -> None:
    """A paraphrase of a disclaimer is a weaker disclaimer."""
    assert SELF_DESCRIPTION == (
        "Kibble is not FLOP Network and not Technocore. It settles nothing."
    )
    assert "Nothing is paid" in SCORE_SELF_DESCRIPTION


def test_the_score_caveat_travels_with_the_record(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    establish_session(mocked_client, mocked_app)

    record = mocked_client.get(STATUS_PATH).json()["adapters"][0]

    assert "score" in record["score_caveat"]
    assert "rank" in record["score_caveat"]


def test_no_response_anywhere_carries_a_third_party_score_or_rank(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """ADR-0007 1 and 10: the number never joins one of our own sentences.

    The caveat *names* the two fields, so the search is for a field rather
    than for the word - which is the difference between "we do not use it" and
    "we do not mention it".
    """
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)
    mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    )

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key in node:
                assert key not in {"score", "rank", "reputation", "eligibility"}, key
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(mocked_client.get(STATUS_PATH).json())


def test_no_module_in_the_package_can_reach_the_recorded_origin(
    api_source_root  # type: ignore[no-untyped-def]
) -> None:
    """The record holds a hostname; nothing turns it into a request.

    The outbound allow-list already confines HTTP to five named modules, and
    none of them mentions this host. Checked from the other direction here.
    """
    from station_api.workscan.kibble import DECLARED_ORIGIN

    for relative in (
        "station_api/technocore/client.py",
        "station_api/technocore/write_client.py",
        "station_api/technocore/evidence_client.py",
        "station_api/opencode/client.py",
        "station_api/workscan/client.py",
    ):
        source = (api_source_root / relative).read_text(encoding="utf-8")
        assert DECLARED_ORIGIN not in source, relative
        assert "kibble" not in source.lower(), relative

    kibble = (api_source_root / "station_api" / "workscan" / "kibble.py").read_text(
        encoding="utf-8"
    )
    assert "httpx" not in kibble
    assert ADAPTERS[0].verified[0].state is VerificationState.VERIFIED


# ---------------------------------------------------------------------------
# The state machine, end to end
# ---------------------------------------------------------------------------


def test_suggested_is_producible_and_the_initial_state_did_not_move() -> None:
    """H1 opened ``suggested``; H2 opened the two this test used to exclude.

    The old name was ``..._and_running_still_is_not``, and H2 built the
    executor that produces ``running`` and ``paused`` (ADR-0008 3). Leaving
    the two exclusions in place would have made this file assert something
    false; deleting the test would have dropped the claim it exists for, which
    is about H1 and is unchanged.

    So the exclusions were replaced by the assertion they were standing in
    for. What matters to the work scan is that ``INITIAL_STATE`` did **not**
    move: a task the user opened and a candidate a scan proposed are still
    born in different states, which is one of the two independent layers that
    keep them apart (SI-277).
    """
    assert TaskState.SUGGESTED in PRODUCIBLE_STATES
    assert INITIAL_STATE is TaskState.AWAITING_APPROVAL
    assert INITIAL_STATE is not TaskState.SUGGESTED
    # The scan producer is still the only way into ``suggested``, and it is a
    # different method from the one a person uses.
    assert TaskState.SUGGESTED not in {INITIAL_STATE}


def test_the_scan_source_is_registered_and_bound_to_the_suggestion_producer() -> None:
    assert TaskSourceId.PUBLIC_ROOM_SCAN in TaskSourceId
    assert set(SCAN_SOURCES) == {TaskSourceId.PUBLIC_ROOM_SCAN}


def test_the_two_producers_refuse_each_others_sources(engine: Engine) -> None:
    """The structural half of "a scan finding is not an operator request"."""
    service = TaskService(engine=engine)

    with pytest.raises(TaskError) as scan_as_task:
        service.open_task(
            module_id=ModuleId.WORK_SCAN,
            source=TaskSourceId.PUBLIC_ROOM_SCAN,
            content=b"TEST-ONLY",
        )
    assert scan_as_task.value.reason == "source_needs_the_scan_producer"

    with pytest.raises(TaskError) as task_as_scan:
        service.suggest_task(
            module_id=ModuleId.WORK_SCAN,
            source=TaskSourceId.OPERATOR_REQUEST,
            content=b"TEST-ONLY",
        )
    assert task_as_scan.value.reason == "source_is_not_a_scan_source"


def test_the_same_content_gets_a_different_identity_under_the_two_sources(
    engine: Engine,
) -> None:
    """Different ``source_version_id`` for byte-identical content.

    This is what makes "the user's own text is never presented as a public
    finding" structural rather than textual (ADR-0007 7).
    """
    from station_api.tasks.sources import content_sha256

    digest = content_sha256(b"TEST-ONLY identical bytes")

    assert source_version_id(TaskSourceId.OPERATOR_REQUEST, digest) != source_version_id(
        TaskSourceId.PUBLIC_ROOM_SCAN, digest
    )
    del engine


def test_suggesting_a_candidate_opens_a_task_in_suggested_and_approves_nothing(
    mocked_client: TestClient, mocked_app: FastAPI, engine: Engine
) -> None:
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)
    mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    )

    reply = mocked_client.post(
        SUGGEST_PATH,
        json={"candidate_id": candidate_id(ROOM, 1)},
        headers={"X-Station-CSRF": csrf},
    )

    assert reply.status_code == 200
    body = reply.json()
    assert body["state"] == "suggested"
    assert body["source_id"] == TaskSourceId.PUBLIC_ROOM_SCAN.value
    assert body["module_id"] == ModuleId.WORK_SCAN.value

    stored = TaskService(engine=engine).get(body["task_id"])
    assert stored.state is TaskState.SUGGESTED
    assert stored.source_id != TaskSourceId.OPERATOR_REQUEST.value


def test_a_suggested_task_still_has_to_be_approved_by_a_person(
    mocked_client: TestClient, mocked_app: FastAPI, engine: Engine
) -> None:
    """The producer opens work; it does not wave it through (ADR-0007 8)."""
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)
    mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    )
    task_id = mocked_client.post(
        SUGGEST_PATH,
        json={"candidate_id": candidate_id(ROOM, 1)},
        headers={"X-Station-CSRF": csrf},
    ).json()["task_id"]

    service = TaskService(engine=engine)
    assert service.get(task_id).state is TaskState.SUGGESTED

    # The walk forward is the user's, through the ordinary transition.
    moved = service.transition(task_id, TaskState.AWAITING_APPROVAL)
    assert moved.state is TaskState.AWAITING_APPROVAL

    # And it still cannot jump to a state the evidence has not earned.
    with pytest.raises(TaskError):
        service.transition(task_id, TaskState.READY_TO_PUBLISH)


def test_an_unknown_candidate_is_a_refusal_and_nothing_is_substituted(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)
    mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    )

    reply = mocked_client.post(
        SUGGEST_PATH,
        json={"candidate_id": "not-a-candidate"},
        headers={"X-Station-CSRF": csrf},
    )

    assert reply.status_code == 400
    assert "yeniden taramaniz" in reply.json()["detail"]


def test_a_new_scan_replaces_the_selectable_candidates_rather_than_merging(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """A candidate that is no longer in the newest reading must not linger."""
    _with_markers(mocked_app)
    csrf = establish_session(mocked_client, mocked_app)
    mocked_client.post(
        SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
    )
    mocked_client.post(
        SCAN_PATH, json={"rooms": [SECOND_ROOM]}, headers={"X-Station-CSRF": csrf}
    )

    reply = mocked_client.post(
        SUGGEST_PATH,
        json={"candidate_id": candidate_id(ROOM, 1)},
        headers={"X-Station-CSRF": csrf},
    )

    assert reply.status_code == 400


# ---------------------------------------------------------------------------
# The scope on the wire is ours, and the reply cannot rename it
# ---------------------------------------------------------------------------


def _app_with(
    settings: Settings, engine: Engine, documents: dict[str, dict[str, object]]
) -> FastAPI:
    """An application whose scan answers with exactly these documents."""
    service, _ = _service(engine, documents)
    application = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        workscan=service,
    )
    _with_markers(application)
    return application


def test_a_reply_cannot_rename_the_room_it_answers_for(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """SI-282, at the surface the reviewer's probe used.

    Every room answered ``{"room": "lobby", ...}`` and the product reported
    ``last_scan.rooms == ["lobby"]``, put that name on each candidate's source
    reference and into the benefit sentence, and built the candidate identity
    from it. The URL requested was still ``/r/test-only-room``; the *reported
    scope* was the reply's. That is SI-273 (the scope is the user's chosen
    set) and INV-05 (this product does not name that room) at once.
    """
    documents = {
        f"/r/{ROOM}": room_document(room="lobby", messages=[message(7, HELP_LINE)]),
        f"/r/{SECOND_ROOM}": room_document(
            room="lobby", messages=[message(7, HELP_LINE)]
        ),
    }
    application = _app_with(settings, engine, documents)

    with TestClient(application, base_url=base_url) as client:
        csrf = establish_session(client, application)
        reply = client.post(
            SCAN_PATH,
            json={"rooms": [ROOM, SECOND_ROOM]},
            headers={"X-Station-CSRF": csrf},
        )

    assert reply.status_code == 200
    body = reply.json()

    # No room was read, both are named as failures, and nothing collapsed.
    assert body["last_scan"]["rooms"] == []
    failures = {item["room"]: item for item in body["last_scan"]["failures"]}
    assert set(failures) == {ROOM, SECOND_ROOM}
    assert all(item["reason"] == "room_unreadable" for item in failures.values())
    assert body["last_scan"]["candidate_count"] == 0

    # And the name the reply chose does not appear in the response at all.
    assert "lobby" not in reply.text


def test_two_rooms_answering_with_the_same_sequence_stay_two_candidates(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """SI-282's identity half.

    A candidate's identity is a digest over ``(room, seq)``. With the room
    taken from the reply, two different rooms both claiming one name and one
    ``seq`` produced one identity, the second overwrote the first in the
    service's own map, and two genuinely different lines became one row.
    """
    documents = {
        f"/r/{ROOM}": room_document(room=ROOM, messages=[message(7, HELP_LINE)]),
        f"/r/{SECOND_ROOM}": room_document(
            room=SECOND_ROOM, messages=[message(7, HELP_LINE)]
        ),
    }
    application = _app_with(settings, engine, documents)

    with TestClient(application, base_url=base_url) as client:
        csrf = establish_session(client, application)
        body = client.post(
            SCAN_PATH,
            json={"rooms": [ROOM, SECOND_ROOM]},
            headers={"X-Station-CSRF": csrf},
        ).json()

    assert body["last_scan"]["rooms"] == [ROOM, SECOND_ROOM]
    assert body["last_scan"]["candidate_count"] == 2

    identities = {
        candidate["id"]
        for result in body["last_scan"]["results"]
        for candidate in result["candidates"]
    }
    assert identities == {candidate_id(ROOM, 7), candidate_id(SECOND_ROOM, 7)}

    references = sorted(
        candidate["source"]["reference"]
        for result in body["last_scan"]["results"]
        for candidate in result["candidates"]
    )
    assert references[0].startswith(f"{SECOND_ROOM}#7@")
    assert references[1].startswith(f"{ROOM}#7@")


def test_an_unusable_line_does_not_turn_the_whole_scan_into_a_500(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """SI-284. One message with no ``ts`` answered HTTP 500 for ten rooms.

    ``derive_from_room`` sat outside the service's per-room ``try`` and the
    route carried no handler, so ``CandidateError`` reached the ASGI layer and
    every room already read went with it - the exact opposite of the service's
    own heading, "failures are per room, and a failed room is never an empty
    room".
    """
    broken = message(1, HELP_LINE)
    del broken["ts"]
    documents = {
        f"/r/{ROOM}": room_document(room=ROOM, messages=[broken]),
        f"/r/{SECOND_ROOM}": room_document(
            room=SECOND_ROOM, messages=[message(9, DEFECT_LINE)]
        ),
    }
    application = _app_with(settings, engine, documents)

    with TestClient(application, base_url=base_url) as client:
        csrf = establish_session(client, application)
        reply = client.post(
            SCAN_PATH,
            json={"rooms": [ROOM, SECOND_ROOM]},
            headers={"X-Station-CSRF": csrf},
        )

    assert reply.status_code == 200
    body = reply.json()

    # The other room survived, and the unusable line is a visible refusal.
    assert body["last_scan"]["candidate_count"] == 1
    assert body["last_scan"]["refusal_count"] == 1
    results = {item["room"]: item for item in body["last_scan"]["results"]}
    assert results[ROOM]["candidates"] == []
    assert results[ROOM]["lines_read"] == 1
    assert results[ROOM]["refusals"][0]["shape"] == "unusable_source"
    assert results[SECOND_ROOM]["candidates"][0]["source"]["seq"] == 9


def test_a_repeated_sequence_number_is_visible_on_the_wire(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """SI-284. ``lines_read: 2, candidates: 1, refusals: 0`` explained nothing."""
    documents = {
        f"/r/{ROOM}": room_document(
            room=ROOM, messages=[message(5, HELP_LINE), message(5, DEFECT_LINE)]
        ),
    }
    application = _app_with(settings, engine, documents)

    with TestClient(application, base_url=base_url) as client:
        csrf = establish_session(client, application)
        body = client.post(
            SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
        ).json()

    result = body["last_scan"]["results"][0]
    assert result["lines_read"] == 2
    assert len(result["candidates"]) == 1
    assert len(result["refusals"]) == 1
    assert result["refusals"][0]["shape"] == "duplicate_sequence"
    assert result["refusals"][0]["detail"].strip()


# ---------------------------------------------------------------------------
# The two Kibble flags, read off the record rather than off a schema default
# ---------------------------------------------------------------------------


def test_the_kibble_record_itself_says_it_was_never_written_or_contacted() -> None:
    """SI-281's derivation half, which two mutations proved untested.

    Flipping ``AdapterRecord.adapter_written`` or ``.contacted`` to ``True``
    turned **no** test red: the response's two ``False`` values came from the
    ``Literal[False]`` defaults in ``schemas.py``, so the assertion beside
    them was a restatement of a schema constant. This asserts the property.
    """
    record = get_adapter("kibble")

    assert record.adapter_written is False
    assert record.contacted is False
    assert all(item.adapter_written is False for item in ADAPTERS)
    assert all(item.contacted is False for item in ADAPTERS)


def test_the_response_carries_the_records_own_two_flags(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """The route reads them now, so the wire and the record cannot disagree."""
    establish_session(mocked_client, mocked_app)
    record = mocked_client.get(STATUS_PATH).json()["adapters"][0]

    assert record["adapter_written"] is get_adapter("kibble").adapter_written
    assert record["contacted"] is get_adapter("kibble").contacted


def test_the_services_own_words_reach_the_screen_over_the_wire(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """SI-281 says the service's own sentence is carried verbatim.

    It was carried verbatim into a *frontend constant*, transcribed by hand
    from the ADR; the wire carried only the Turkish rendering, and the test
    that claimed to check it asserted two module constants. A quotation kept
    in two places drifts in the copy nobody diffs, so it is on the record and
    therefore in the response.
    """
    establish_session(mocked_client, mocked_app)
    record = mocked_client.get(STATUS_PATH).json()["adapters"][0]

    assert record["self_description_source"] == SELF_DESCRIPTION
    assert record["score_self_description"] == SCORE_SELF_DESCRIPTION
    assert record["self_description"].strip()


def test_a_reply_borrowing_another_rooms_name_cannot_collapse_two_candidates(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """SI-282's identity half, in the shape the reviewer's probe produced.

    ``alpha`` and ``beta`` were both scanned; ``beta``'s reply claimed to be
    ``alpha`` and reused ``alpha``'s ``seq``. With the room read off the
    reply, both lines hashed to one ``candidate_id``, the second overwrote the
    first in the service's own map, and two rooms' worth of reading came back
    as one selectable row - while ``results`` still listed two rooms with the
    same name.

    Now the borrowed name refuses the document, so the second room is a named
    failure and the first is untouched. The invariant the assertions state is
    the one that has to hold either way: one identity per reported candidate,
    and no room reported twice.
    """
    documents = {
        f"/r/{ROOM}": room_document(room=ROOM, messages=[message(7, HELP_LINE)]),
        f"/r/{SECOND_ROOM}": room_document(
            room=ROOM, messages=[message(7, DEFECT_LINE)]
        ),
    }
    application = _app_with(settings, engine, documents)

    with TestClient(application, base_url=base_url) as client:
        csrf = establish_session(client, application)
        body = client.post(
            SCAN_PATH,
            json={"rooms": [ROOM, SECOND_ROOM]},
            headers={"X-Station-CSRF": csrf},
        ).json()

    scan = body["last_scan"]
    reported = [result["room"] for result in scan["results"]]
    identities = [
        candidate["id"]
        for result in scan["results"]
        for candidate in result["candidates"]
    ]

    assert len(reported) == len(set(reported)), "a room was reported twice"
    assert len(identities) == len(set(identities)), "two candidates share an identity"
    assert len(identities) == scan["candidate_count"]

    # And what actually happened: the borrowed name refused that room by name.
    assert scan["rooms"] == [ROOM]
    failures = {item["room"]: item for item in scan["failures"]}
    assert failures[SECOND_ROOM]["reason"] == "room_unreadable"


# ---------------------------------------------------------------------------
# The two backstops under the per-line guard, exercised by fault injection
# ---------------------------------------------------------------------------
#
# Nothing reachable raises past the per-line refusal any more, which is the
# point of fixing it there - and it also means these two layers would be
# untested by any document a transport can answer with. They are the layers
# that decide whether a *future* refusal is one room or the whole scan, so the
# failure is injected rather than left to a later reviewer to discover the way
# this one was.


def test_a_derivation_that_fails_outright_costs_one_room_and_not_the_scan(
    settings: Settings, engine: Engine, base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SI-284, service layer. A failed room is named; the others still count."""
    from station_api.workscan import service as service_module

    real = service_module.derive_from_room
    calls: list[str] = []

    def failing(snapshot, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(snapshot.room)
        if snapshot.room == ROOM:
            raise CandidateError("TEST-ONLY: derivation refused")
        return real(snapshot, **kwargs)

    monkeypatch.setattr(service_module, "derive_from_room", failing)

    documents = {
        f"/r/{ROOM}": room_document(room=ROOM, messages=[message(1, HELP_LINE)]),
        f"/r/{SECOND_ROOM}": room_document(
            room=SECOND_ROOM, messages=[message(9, DEFECT_LINE)]
        ),
    }
    application = _app_with(settings, engine, documents)

    with TestClient(application, base_url=base_url) as client:
        csrf = establish_session(client, application)
        reply = client.post(
            SCAN_PATH,
            json={"rooms": [ROOM, SECOND_ROOM]},
            headers={"X-Station-CSRF": csrf},
        )

    assert calls == [ROOM, SECOND_ROOM]
    assert reply.status_code == 200
    scan = reply.json()["last_scan"]

    assert scan["rooms"] == [SECOND_ROOM]
    assert scan["candidate_count"] == 1
    failures = {item["room"]: item for item in scan["failures"]}
    assert failures[ROOM]["reason"] == "room_underivable"


def test_a_scan_that_fails_as_a_whole_answers_502_and_not_500(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """SI-284, route layer.

    ``scan`` reports a failed *room* rather than raising, so this handler is
    for the case that is not one room. Without it the answer is a generic 500
    from the ASGI layer, which tells a user nothing about what was read - and
    that is exactly what an unusable line used to produce.
    """
    service, _ = _service(engine)

    def refusing(*args: object, **kwargs: object) -> ScanResult:
        raise WorkScanError("TEST-ONLY: the scan could not run")

    application = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        workscan=service,
    )
    _with_markers(application)
    service.scan = refusing  # type: ignore[method-assign]

    with TestClient(application, base_url=base_url, raise_server_exceptions=False) as client:
        csrf = establish_session(client, application)
        reply = client.post(
            SCAN_PATH, json={"rooms": [ROOM]}, headers={"X-Station-CSRF": csrf}
        )

    assert reply.status_code == 502
    assert reply.json()["detail"] == "TEST-ONLY: the scan could not run"


def test_the_status_document_says_the_prohibitions_are_pattern_matched(
    mocked_client: TestClient, mocked_app: FastAPI
) -> None:
    """SI-283's honesty half, on the surface rather than in a document.

    ADR-0007 8 and ``work-scan.md`` called the six shapes "structurally
    blocked". The ordering is structural - a prohibition is matched before any
    signal, on every path - but the matching is a pattern list, and a review
    walked nineteen lines past it. The stronger word is corrected in the
    documents; the user is told on the screen.
    """
    establish_session(mocked_client, mocked_app)
    body = mocked_client.get(STATUS_PATH).json()

    assert body["prohibition_statement"] == PROHIBITION_HONESTY_SENTENCE
    assert "kalip eslesmesiyle" in body["prohibition_statement"]
    # Still shown beside the derivation sentence, not instead of it.
    assert body["honesty"] == DERIVATION_HONESTY_SENTENCE
