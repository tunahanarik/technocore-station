"""The fourth outbound client: the transport rules, and the credential's.

Three clients already carry the rules this one repeats - one origin, no URL
parameter, no TLS setting, no followed redirect, a streamed cap, bounded
attempts. They are asserted again here rather than assumed, because a rule
that holds in three modules and not the fourth is worse than a rule nobody
wrote down: it reads as covered.

And two things are genuinely new, so they get the sharpest tests in the file:

* this is the only client that attaches a **credential**, so its headers are
  checked for what they carry *and* for what they must not;
* a request here may **cost money**, so the attempt count is measured on the
  metered lane rather than reasoned about.
"""

from __future__ import annotations

import ast
import gzip
import inspect
from pathlib import Path

import httpx
import pytest
from station_api.opencode import client as client_module
from station_api.opencode.client import (
    AUTH_HEADER_NAME,
    AUTH_SCHEME,
    MAX_CATALOG_ATTEMPTS,
    MAX_METERED_ATTEMPTS,
    MAX_RETRY_AFTER_SECONDS,
    SESSION_HEADER_NAME,
    TIMEOUT,
    USER_AGENT,
    OpenCodeClient,
    assert_allowed_url,
)
from station_api.opencode.errors import (
    OpenCodeLostResponseError,
    OpenCodeRequestError,
    ResponseTooLargeError,
    UnexpectedRedirectError,
)
from station_api.opencode.registry import (
    ENDPOINTS,
    OPENCODE_ORIGIN,
    EndpointId,
    Protocol,
    get_endpoint,
)

from tests.security.opencode_fixtures import (
    catalog_transport,
    recording_transport,
    refusing_transport,
    status_transport,
)

pytestmark = pytest.mark.security

TEST_ONLY_CREDENTIAL = "TEST-ONLY-client-credential-0001"


def _client(transport: httpx.MockTransport) -> OpenCodeClient:
    return OpenCodeClient(transport=transport, sleep=lambda _: None)


# ---------------------------------------------------------------------------
# The origin allow-list
# ---------------------------------------------------------------------------


def test_every_way_around_the_allow_list_is_refused() -> None:
    """Scheme, host, port, user-info, query, fragment and traversal.

    The trailing-dot host is here on purpose: ``opencode.ai.`` resolves the
    same and is a different string, which is the classic way past a naive
    allow-list.
    """
    for url in (
        "http://opencode.ai/zen/go/v1/models",
        "https://evil.example/zen/go/v1/models",
        "https://opencode.ai.evil.example/zen/go/v1/models",
        "https://opencode.ai./zen/go/v1/models",
        "https://user:pass@opencode.ai/zen/go/v1/models",
        "https://opencode.ai:8443/zen/go/v1/models",
        "https://opencode.ai/zen/go/v1/../../secret",
        "https://opencode.ai/zen/go/v1/models#fragment",
        "https://opencode.ai/zen/go/v1/models?key=leak",
        "https://127.0.0.1/zen/go/v1/models",
    ):
        with pytest.raises(OpenCodeRequestError):
            assert_allowed_url(url)


def test_the_registered_addresses_all_pass_the_allow_list() -> None:
    """Without this the loop above could be refusing everything."""
    for endpoint in ENDPOINTS:
        assert_allowed_url(endpoint.url)
        assert endpoint.url.startswith(f"{OPENCODE_ORIGIN}/zen/go/v1/")


def test_a_query_string_is_refused_because_a_key_could_ride_in_one() -> None:
    """Stated separately from the loop, because the reason is specific.

    The Technocore clients refuse user-info and fragments; this one also
    refuses a query, because a query is where a credential ends up when
    somebody "just adds ``?api_key=``" - and a URL is logged in more places
    than a header is.
    """
    with pytest.raises(OpenCodeRequestError):
        assert_allowed_url(f"{OPENCODE_ORIGIN}/zen/go/v1/models?api_key=x")


# ---------------------------------------------------------------------------
# No URL, no method, no TLS setting
# ---------------------------------------------------------------------------


def test_the_client_takes_no_url_method_or_tls_setting() -> None:
    """The parameter list is the API's promise; this reads it."""
    forbidden = {"url", "method", "verify", "headers", "cert", "trust_env", "retries"}

    signatures = [
        inspect.signature(OpenCodeClient.__init__),
        inspect.signature(OpenCodeClient.fetch_catalog),
        inspect.signature(OpenCodeClient.post_completion),
    ]
    for signature in signatures:
        assert not (set(signature.parameters) & forbidden), signature


def test_tls_verification_is_never_disabled() -> None:
    """``verify`` is not merely True: it is never named in the package.

    A parameter that is never written cannot be flipped, which is a stronger
    property than a default nobody changed.
    """
    package = Path(client_module.__file__ or "").parent
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "verify=" not in source, path.name
        assert "verify =" not in source, path.name


def test_a_transport_with_tls_verification_off_cannot_be_injected() -> None:
    """Only a ``MockTransport`` is accepted, so no real TLS posture arrives."""
    with pytest.raises(TypeError):
        OpenCodeClient(transport=httpx.HTTPTransport(verify=False))  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        OpenCodeClient(transport=httpx.HTTPTransport())  # type: ignore[arg-type]


def test_every_timeout_phase_is_bounded() -> None:
    """No phase inherits "no limit"."""
    assert TIMEOUT.connect is not None
    assert TIMEOUT.read is not None
    assert TIMEOUT.write is not None
    assert TIMEOUT.pool is not None


# ---------------------------------------------------------------------------
# What the request carries, and what it must not
# ---------------------------------------------------------------------------


def test_the_catalog_request_carries_no_credential_at_all() -> None:
    """It answers without one, so attaching one would be pointless exposure."""
    transport, recorder = catalog_transport()
    _client(transport).fetch_catalog()

    assert recorder.count == 1
    assert AUTH_HEADER_NAME.lower() not in {
        name.lower() for name in recorder.last.headers
    }


def test_a_metered_request_carries_the_credential_in_one_named_header() -> None:
    transport, recorder = recording_transport(
        lambda _: httpx.Response(200, content=b'{"choices": []}')
    )
    _client(transport).post_completion(
        Protocol.CHAT_COMPLETIONS, b"{}", api_key=TEST_ONLY_CREDENTIAL
    )

    header = recorder.last.headers[AUTH_HEADER_NAME]
    assert header == f"{AUTH_SCHEME} {TEST_ONLY_CREDENTIAL}"


def test_the_outbound_request_carries_no_identity_cookie_or_csrf_value() -> None:
    """SI-71's rule, narrowed for this lane (ADR-0005 6).

    The Technocore invariant is "no credential at all". That cannot be the
    rule here, because the whole point of this client is to send one. The
    narrowed rule is: **the provider credential and nothing else** - no DID,
    no CSRF value, no session cookie, no data-directory path, no machine
    name.
    """
    transport, recorder = recording_transport(
        lambda _: httpx.Response(200, content=b"{}")
    )
    _client(transport).post_completion(
        Protocol.MESSAGES, b"{}", api_key=TEST_ONLY_CREDENTIAL
    )

    names = {name.lower() for name in recorder.last.headers}
    for forbidden in ("cookie", "x-station-csrf", "x-station-request-id", "referer"):
        assert forbidden not in names

    rendered = "\n".join(
        f"{name}: {value}" for name, value in recorder.last.headers.items()
    ).lower()
    for marker in ("did:key", "c:\\", "appdata", "localappdata", "station_session"):
        assert marker not in rendered


def test_the_session_header_is_sent_and_is_not_tied_to_anything() -> None:
    """The documentation asks for it; ADR-0005 3 bounds what it may be.

    Random per client instance, hex, and different between two clients - so
    it identifies a run of the program and links nothing across runs, users
    or identities.
    """
    transport, recorder = catalog_transport()
    first = _client(transport)
    first.fetch_catalog()
    sent = recorder.last.headers[SESSION_HEADER_NAME]

    assert sent == first.session_id
    assert len(sent) == 32
    assert all(character in "0123456789abcdef" for character in sent)

    second = _client(transport)
    assert second.session_id != first.session_id


def test_the_user_agent_is_ours_and_impersonates_nobody() -> None:
    transport, recorder = catalog_transport()
    _client(transport).fetch_catalog()

    agent = recorder.last.headers["User-Agent"]
    assert agent == USER_AGENT
    assert agent.startswith("TechnocoreStation/")
    lowered = agent.lower()
    for impersonated in ("opencode", "curl", "python-httpx", "mozilla", "openai"):
        assert impersonated not in lowered


def test_the_credential_header_is_written_in_exactly_one_module(
    api_source_root: Path,
) -> None:
    """One line to change when the contract is published (ADR-0005 3).

    A second spelling anywhere would be a second thing to update and a second
    place a credential could be attached without review.
    """
    offenders: list[str] = []
    allowed = Path(client_module.__file__ or "").resolve()

    for path in api_source_root.rglob("*.py"):
        if path.resolve() == allowed:
            continue
        for value in _string_literals(path):
            lowered = value.lower()
            if lowered == "authorization" or lowered.startswith("bearer "):
                offenders.append(f"{path.relative_to(api_source_root)}: {value!r}")

    assert offenders == [], f"a credential header is written elsewhere: {offenders}"


def _string_literals(path: Path) -> list[str]:
    """Every string constant in a file, **minus its docstrings**.

    Prose is not a header. Two modules explain in their docstrings that the
    credential header is written in exactly one place, and a scan that
    counted those sentences as violations would have made the honest
    documentation the thing to delete.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))

    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_the_unverified_header_assumption_is_labelled_where_it_lives() -> None:
    """The assumption is only honest if it is visible.

    Checked on the source rather than trusted, because a comment is exactly
    the thing a later edit drops while keeping the line it explained.
    """
    source = Path(client_module.__file__ or "").read_text(encoding="utf-8")
    assert "NOT VERIFIED IN THE OFFICIAL DOCUMENTATION" in source
    assert "ADR-0005 3" in source
    assert "dogrulanmamistir" in client_module.AUTH_HEADER_CAVEAT


# ---------------------------------------------------------------------------
# Transport behaviour
# ---------------------------------------------------------------------------


def test_a_redirect_is_never_followed() -> None:
    transport, recorder = status_transport(
        302, body=b"", headers={"location": "https://evil.example/collect"}
    )
    with pytest.raises(UnexpectedRedirectError):
        _client(transport).fetch_catalog()

    assert recorder.count == 1
    assert "evil.example" not in " ".join(recorder.urls())


def test_a_body_over_the_cap_is_refused_on_decompressed_bytes() -> None:
    """A small gzip that expands past the cap is refused, not buffered."""
    endpoint = get_endpoint(EndpointId.MODELS)
    bomb = gzip.compress(b"\0" * (endpoint.max_bytes + 4096))
    assert len(bomb) < endpoint.max_bytes

    transport, _ = recording_transport(
        lambda _: httpx.Response(
            200, content=bomb, headers={"content-encoding": "gzip"}
        )
    )
    with pytest.raises(ResponseTooLargeError):
        _client(transport).fetch_catalog()


def test_the_free_catalog_is_retried_a_bounded_number_of_times() -> None:
    transport, recorder = status_transport(503, body=b"")

    with pytest.raises(OpenCodeRequestError):
        _client(transport).fetch_catalog()

    assert recorder.count == MAX_CATALOG_ATTEMPTS


def test_a_retry_after_header_is_honoured_but_clamped() -> None:
    waits: list[float] = []
    transport, _ = status_transport(429, body=b"", headers={"retry-after": "9000"})
    client = OpenCodeClient(transport=transport, sleep=waits.append)

    with pytest.raises(OpenCodeRequestError):
        client.fetch_catalog()

    assert waits
    assert max(waits) <= MAX_RETRY_AFTER_SECONDS


@pytest.mark.parametrize("protocol", list(Protocol))
def test_a_metered_request_is_attempted_exactly_once_on_a_retryable_status(
    protocol: Protocol,
) -> None:
    """The rule the read client does not have, and the reason it does not.

    A 429 or a 503 is transient on a public document and worth a second ask.
    Here the first request may already have been billed, so a retry turns one
    possible charge into two (ADR-0005 11).
    """
    for status_code in (429, 500, 503):
        transport, recorder = status_transport(status_code, body=b"{}")
        _client(transport).post_completion(
            protocol, b"{}", api_key=TEST_ONLY_CREDENTIAL
        )
        assert recorder.count == MAX_METERED_ATTEMPTS == 1


def test_a_lost_response_on_a_metered_lane_is_named_rather_than_retried() -> None:
    """"We do not know whether that was charged" is the honest sentence."""
    transport, recorder = refusing_transport(httpx.ReadTimeout("simulated"))

    with pytest.raises(OpenCodeLostResponseError) as caught:
        _client(transport).post_completion(
            Protocol.RESPONSES, b"{}", api_key=TEST_ONLY_CREDENTIAL
        )

    assert recorder.count == 1
    assert "tekrarlanmaz" in str(caught.value)


def test_the_module_contains_no_retry_loop_on_the_metered_path() -> None:
    """Structural, so the behaviour above cannot be reintroduced by a helper.

    ``_with_bounded_retry`` refuses a metered endpoint outright, and this
    reads that refusal off the syntax tree rather than trusting the comment
    beside it.
    """
    source = Path(client_module.__file__ or "").read_text(encoding="utf-8")
    tree = ast.parse(source)

    guard_found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_with_bounded_retry":
            body = ast.unparse(node)
            assert "endpoint.metered" in body
            guard_found = True
    assert guard_found, "the retry helper disappeared; this test now proves nothing"

    post = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "post_completion"
    )
    for node in ast.walk(post):
        assert not isinstance(node, (ast.For, ast.While)), "a metered retry loop"


def test_an_excerpt_of_an_error_body_is_bounded_and_swept() -> None:
    """An upstream body is data, never our sentence, and never unbounded."""
    hostile = b'{"error": {"message": "' + b"A" * 5000 + b'\\u0000"}}'
    transport, _ = status_transport(400, body=hostile)
    raw = _client(transport).post_completion(
        Protocol.CHAT_COMPLETIONS, b"{}", api_key=TEST_ONLY_CREDENTIAL
    )

    excerpt = raw.excerpt
    assert len(excerpt) <= client_module.MAX_EXCERPT_CHARS
    assert "\x00" not in excerpt
