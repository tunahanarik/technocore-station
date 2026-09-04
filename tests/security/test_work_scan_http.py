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
from station_api.workscan.kibble import (
    ADAPTERS,
    SCORE_SELF_DESCRIPTION,
    SELF_DESCRIPTION,
    TABLE_PROVENANCE,
    AdapterSupport,
    VerificationState,
)
from station_api.workscan.service import MAX_ROOMS_PER_SCAN, WorkScanService

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


def test_suggested_is_producible_and_running_still_is_not() -> None:
    assert TaskState.SUGGESTED in PRODUCIBLE_STATES
    assert TaskState.RUNNING not in PRODUCIBLE_STATES
    assert TaskState.PAUSED not in PRODUCIBLE_STATES
    assert INITIAL_STATE is TaskState.AWAITING_APPROVAL


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
