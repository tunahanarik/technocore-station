"""SI-271, SI-272, SI-273 - the fourth registry and the fifth outbound client.

The properties here are the ones the four earlier clients established, plus
the two this one adds: a query string that is **built** rather than accepted,
and a success signal that is the Content-Type rather than the status code.
"""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest
from station_api.technocore.client import ReadOnlyTechnocoreClient
from station_api.technocore.sources import TECHNOCORE_ORIGIN
from station_api.technocore.write_targets import DENIED_ROOMS
from station_api.workscan import client as client_module
from station_api.workscan.client import (
    MAX_ATTEMPTS,
    MAX_RETRY_AFTER_SECONDS,
    USER_AGENT,
    RoomScanClient,
    assert_allowed_query,
    assert_allowed_url,
)
from station_api.workscan.errors import (
    ScanFetchError,
    ScanTargetError,
    UnexpectedRedirectError,
    WorkScanError,
    WrongMediaTypeError,
)
from station_api.workscan.targets import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MIN_LIMIT,
    NEVER_SENT_PARAMS,
    ROOM_INDEX_PATH,
    SCAN_TARGETS,
    RoomScanTarget,
    ScanTargetId,
    clamp_limit,
    index_query,
    messages_query,
    resolve_room_target,
)

from tests.security.workscan_fixtures import (
    MARKERS,
    ROOM,
    body_bytes,
    index_document,
    json_transport,
    recording_transport,
    refusing_transport,
    room_document,
    status_transport,
)

pytestmark = pytest.mark.security


def _target() -> RoomScanTarget:
    return resolve_room_target(ROOM, markers=MARKERS)


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------


def test_the_registry_holds_exactly_the_two_addresses_the_adr_opened() -> None:
    """Two, and the discovery lane is not one of them.

    ``/r/events`` is out of scope because its published schema carries
    ``parameters: null`` and describes its query only in prose (ADR-0007 3).
    Asserted rather than commented, so adding it is a visible change here.
    """
    assert {target.id for target in SCAN_TARGETS} == {
        ScanTargetId.ROOM_INDEX,
        ScanTargetId.ROOM_MESSAGES,
    }
    paths = {target.path for target in SCAN_TARGETS}
    assert paths == {"/rooms", "/r/{room}"}
    assert "/r/events" not in paths
    for target in SCAN_TARGETS:
        assert target.method == "GET"
        assert target.media == "application/json"
        assert target.rationale.strip()


def test_the_six_document_registry_did_not_grow(api_source_root: Path) -> None:
    """The reason a fourth registry exists at all.

    ``SOURCES`` is what keeps the monitoring path from addressing a room, and
    the property is pinned by its length and its identifier set. H1 added an
    address; it must not have added one *there*.
    """
    from station_api.technocore.sources import SOURCES, SourceId

    assert len(SOURCES) == 6
    assert {source.id for source in SOURCES} == set(SourceId)
    assert all("/r/" not in source.path for source in SOURCES)
    assert all(source.path != ROOM_INDEX_PATH for source in SOURCES)
    del api_source_root


def test_the_read_clients_fetch_signature_is_unchanged() -> None:
    """The fifth client did not borrow the third one's shape.

    ``ReadOnlyTechnocoreClient.fetch(source)`` is pinned elsewhere and pinned
    again here from the other direction: the scan client's methods take
    different names and different arguments, so nothing invites a caller to
    treat the two as interchangeable.
    """
    import inspect

    read = inspect.signature(ReadOnlyTechnocoreClient.fetch)
    assert list(read.parameters) == ["self", "source"]

    scan_index = inspect.signature(RoomScanClient.fetch_room_index)
    scan_messages = inspect.signature(RoomScanClient.fetch_room_messages)
    assert list(scan_index.parameters) == ["self", "limit"]
    assert list(scan_messages.parameters) == ["self", "target", "since", "limit"]
    assert not hasattr(RoomScanClient, "fetch")


# ---------------------------------------------------------------------------
# The room policy, applied to a read
# ---------------------------------------------------------------------------


def test_the_denied_rooms_are_refused_on_the_read_path_too() -> None:
    """ADR-0007 3 and 11: ``DENIED_ROOMS`` applies to reading as well.

    Not merely absent from the fixtures - refused by the product, so a user
    cannot type it either.
    """
    assert "lobby" in DENIED_ROOMS

    for room in sorted(DENIED_ROOMS):
        with pytest.raises(ScanTargetError):
            resolve_room_target(room, markers=MARKERS)


def test_a_room_name_outside_the_published_pattern_is_refused() -> None:
    for bad in ("UPPER", "-leading", "a" * 49, "has space", ""):
        with pytest.raises(ScanTargetError):
            resolve_room_target(bad, markers=MARKERS)


def test_no_markers_means_every_room_is_refused() -> None:
    """Fail-closed: an unverified convention resolves nothing."""
    with pytest.raises(ScanTargetError):
        resolve_room_target(ROOM, markers=frozenset())


def test_the_resolved_target_builds_its_url_from_the_origin_constant() -> None:
    target = _target()
    assert target.url == f"{TECHNOCORE_ORIGIN}/r/{ROOM}"
    assert_allowed_url(target.url)


# ---------------------------------------------------------------------------
# Pagination, read off the pinned document
# ---------------------------------------------------------------------------


def test_the_limit_is_clamped_and_never_refused() -> None:
    """The published rule: clamped to 1..200, never refused."""
    assert clamp_limit(0) == MIN_LIMIT
    assert clamp_limit(-5) == MIN_LIMIT
    assert clamp_limit(10_000) == MAX_LIMIT
    assert clamp_limit(50) == 50
    assert DEFAULT_LIMIT == 50

    # And the clamp reaches the wire value, so the recorded limit is the sent
    # one rather than the asked-for one.
    assert index_query(limit=10_000)["limit"] == str(MAX_LIMIT)
    assert messages_query(limit=0)["limit"] == str(MIN_LIMIT)


def test_the_format_parameter_is_always_json_and_never_anything_else() -> None:
    assert index_query()["format"] == "json"
    assert messages_query()["format"] == "json"


def test_a_negative_cursor_is_refused_rather_than_handed_to_the_fallback() -> None:
    """The server reads an invalid cursor as *no* cursor and returns the newest.

    Relying on that would mean a silent "here is the newest slice" whenever a
    caller made an arithmetic mistake.
    """
    with pytest.raises(ScanTargetError):
        messages_query(since=-1)

    assert "since" not in messages_query()
    assert messages_query(since=0)["since"] == "0"


def test_the_long_poll_parameter_is_never_sent(tmp_path: Path) -> None:
    """ADR-0007 4: no ``wait``, anywhere, on any path.

    Three ways at once, because a rule kept only by intention comes back: the
    parameter is on a refusal list, the query builders never emit it, and the
    package's syntax tree contains no string literal that spells it as a
    parameter name.
    """
    del tmp_path
    assert "wait" in NEVER_SENT_PARAMS

    for query in (index_query(), messages_query(since=3, limit=200)):
        assert set(query) <= {"limit", "format", "since"}
        assert "wait" not in query
        assert "n" not in query

    with pytest.raises(ScanFetchError):
        assert_allowed_query({"limit": "50", "wait": "10"})


def test_no_module_in_the_package_names_wait_as_a_query_parameter(
    api_source_root: Path,
) -> None:
    """The structural half of the polling ban.

    A ``"wait"`` literal anywhere outside the refusal list would be the first
    half of a long-poll. Docstrings are skipped, so the prose that explains
    the rule cannot trip the rule.
    """
    package = api_source_root / "station_api" / "workscan"
    offenders: list[str] = []

    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            if node.value == "wait" and path.name != "targets.py":
                offenders.append(f"{path.name}:{node.lineno}")

    assert offenders == [], f"a long-poll parameter appears in {offenders}"


def test_the_package_starts_no_timer_or_background_task(
    api_source_root: Path,
) -> None:
    """No scheduler, no thread, no task, no sleep loop (ADR-0007 4).

    Read off the syntax tree rather than argued: an import is the cheapest
    possible evidence and the hardest to talk your way past.
    """
    package = api_source_root / "station_api" / "workscan"
    banned_imports = ("asyncio", "threading", "sched", "concurrent", "time")
    banned_calls = ("create_task", "Timer", "Thread", "call_later", "run_forever")
    offenders: list[str] = []

    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                if isinstance(node, ast.Attribute) and node.attr in banned_calls:
                    offenders.append(f"{path.name}: {node.attr}")
                continue
            for name in names:
                if any(
                    name == item or name.startswith(f"{item}.")
                    for item in banned_imports
                ):
                    # ``time`` is permitted in exactly one place: the retry
                    # sleep inside the client, which is a bounded wait between
                    # two attempts of one request and not a schedule.
                    if name == "time" and path.name == "client.py":
                        continue
                    offenders.append(f"{path.name}: {name}")

    assert offenders == [], f"the package grew a scheduler: {offenders}"


# ---------------------------------------------------------------------------
# The allow-list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://technocore.chat/rooms",
        "https://evil.example/rooms",
        "https://technocore.chat.evil.example/rooms",
        "https://technocore.chat./rooms",
        "https://user:pass@technocore.chat/rooms",
        "https://technocore.chat:8443/rooms",
        "https://technocore.chat/rooms#frag",
        "https://technocore.chat/r/../admin",
        "https://technocore.chat/rooms?format=json",
    ],
)
def test_every_way_around_the_allow_list_is_refused(url: str) -> None:
    """Including a query, which this client is the first to send.

    The query goes to httpx as typed parameters. A URL that already carries
    one means somebody built an address by concatenation, which is the step
    the registry exists to remove.
    """
    with pytest.raises(ScanFetchError):
        assert_allowed_url(url)


def test_the_client_takes_no_url_method_or_tls_setting() -> None:
    import inspect

    parameters = inspect.signature(RoomScanClient.__init__).parameters
    assert set(parameters) == {"self", "transport", "sleep"}


def test_a_transport_with_tls_verification_off_cannot_be_injected() -> None:
    with pytest.raises(TypeError):
        RoomScanClient(transport=httpx.HTTPTransport(verify=False))  # type: ignore[arg-type]


def test_tls_verification_is_never_disabled(api_source_root: Path) -> None:
    """``verify`` is not written anywhere in the package."""
    package = api_source_root / "station_api" / "workscan"
    for path in sorted(package.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "verify=" not in source, path.name
        assert "_create_unverified_context" not in source, path.name


# ---------------------------------------------------------------------------
# Behaviour on the wire
# ---------------------------------------------------------------------------


def test_a_room_read_sends_one_get_with_the_built_query() -> None:
    transport, recorder = json_transport(room_document())
    client = RoomScanClient(transport=transport, sleep=lambda _: None)

    result = client.fetch_room_messages(_target(), since=4, limit=10)

    assert recorder.count == 1
    request = recorder.last
    assert request.method == "GET"
    assert request.url.path == f"/r/{ROOM}"
    assert dict(request.url.params) == {"limit": "10", "format": "json", "since": "4"}
    assert result.target_id is ScanTargetId.ROOM_MESSAGES
    assert result.query == {"limit": "10", "format": "json", "since": "4"}


def test_the_outbound_request_carries_no_identity_cookie_or_credential() -> None:
    """Reading a public room needs no credential, and this client has none."""
    transport, recorder = json_transport(index_document())
    client = RoomScanClient(transport=transport, sleep=lambda _: None)

    client.fetch_room_index()

    headers = {name.lower() for name in recorder.last.headers}
    assert "authorization" not in headers
    assert "cookie" not in headers
    assert "x-station-csrf" not in headers
    assert recorder.last.headers["user-agent"] == USER_AGENT


def test_a_redirect_is_an_error_and_the_location_is_not_followed() -> None:
    transport, recorder = status_transport(
        302, headers={"location": "https://evil.example/rooms"}
    )
    client = RoomScanClient(transport=transport, sleep=lambda _: None)

    with pytest.raises(UnexpectedRedirectError):
        client.fetch_room_index()

    assert recorder.count == 1
    assert "evil.example" not in recorder.urls()[0]


def test_a_two_hundred_carrying_plain_text_is_refused_by_media_type() -> None:
    """The reason the status code cannot be the success signal.

    ``format=json`` is advisory on this service: an ignored value leaves a 200
    carrying ``text/plain``. A client that trusted the status would hand prose
    to a JSON parser and report a parse error for a contract mismatch.
    """
    transport, _ = status_transport(
        200,
        body=b"# rooms\nlobby  12 messages\n",
        headers={"content-type": "text/plain; charset=utf-8"},
    )
    client = RoomScanClient(transport=transport, sleep=lambda _: None)

    with pytest.raises(WrongMediaTypeError) as caught:
        client.fetch_room_index()

    assert "format=json" in str(caught.value)


def test_a_json_content_type_with_a_charset_is_accepted() -> None:
    """The media type is compared before its parameters; a charset is normal."""
    transport, _ = recording_transport(
        lambda _: httpx.Response(
            200,
            content=body_bytes(index_document()),
            headers={"content-type": "application/json; charset=utf-8"},
        )
    )
    client = RoomScanClient(transport=transport, sleep=lambda _: None)

    assert client.fetch_room_index().content_type.startswith("application/json")


def test_a_retryable_status_is_attempted_a_bounded_number_of_times() -> None:
    transport, recorder = status_transport(503)
    client = RoomScanClient(transport=transport, sleep=lambda _: None)

    with pytest.raises(ScanFetchError):
        client.fetch_room_index()

    assert recorder.count == MAX_ATTEMPTS == 2


def test_a_retry_after_header_is_honoured_but_clamped() -> None:
    waits: list[float] = []
    transport, _ = status_transport(429, headers={"retry-after": "3600"})
    client = RoomScanClient(transport=transport, sleep=waits.append)

    with pytest.raises(ScanFetchError):
        client.fetch_room_index()

    assert waits and max(waits) <= MAX_RETRY_AFTER_SECONDS


def test_a_transport_failure_is_named_rather_than_swallowed() -> None:
    transport, _ = refusing_transport(httpx.ConnectError("TEST-ONLY"))
    client = RoomScanClient(transport=transport, sleep=lambda _: None)

    with pytest.raises(ScanFetchError):
        client.fetch_room_index()


def test_the_client_catches_nothing_that_could_hide_the_network_guard() -> None:
    """A guard is only as good as the assumption behind it.

    If this module ever grew a bare ``except Exception`` the outbound-guard
    probe would keep passing while testing nothing, so the handled types are
    read off the source and checked to be the narrow ones.
    """
    source = Path(client_module.__file__ or "").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        assert node.type is not None, "a bare except would swallow the guard"
        names = (
            [ast.unparse(element) for element in node.type.elts]
            if isinstance(node.type, ast.Tuple)
            else [ast.unparse(node.type)]
        )
        for name in names:
            assert name not in {"Exception", "BaseException", "AssertionError"}, name


def test_the_scan_errors_are_not_subclasses_of_the_guards_exception() -> None:
    """The outbound guard must escape this client's error handling."""
    from tests.conftest import OutboundNetworkBlockedError

    for absorbed in (WorkScanError, ScanFetchError, httpx.TransportError):
        assert not issubclass(OutboundNetworkBlockedError, absorbed)
