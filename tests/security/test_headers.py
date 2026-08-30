"""SI-25 .. SI-33 - CORS absence and security headers."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.security

CORS_HEADER_PREFIX = "access-control-"


def test_no_cors_headers_in_any_response(client: TestClient, app: FastAPI) -> None:
    """Not one response may carry a CORS header, on any status code."""
    token = app.state.bootstrap_tokens.issue()

    responses = [
        client.get("/api/health"),
        client.get("/api/app/status"),  # 401
        client.get("/api/health", headers={"Host": "evil.example"}),  # 421
        client.get("/api/health", headers={"Origin": "http://evil.example"}),  # 403
        client.get(f"/session/{token}", follow_redirects=False),  # 303
    ]

    for response in responses:
        offenders = [h for h in response.headers if h.lower().startswith(CORS_HEADER_PREFIX)]
        assert offenders == [], f"CORS header leaked: {offenders}"


def test_preflight_is_not_answered(client: TestClient) -> None:
    """Without CORS middleware there is no preflight handler to answer."""
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in {h.lower() for h in response.headers}


def test_no_cors_middleware_in_source_tree(api_source_root: Path) -> None:
    offenders: list[str] = []
    for path in api_source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "CORSMiddleware" in text or "Access-Control-Allow" in text:
            offenders.append(str(path))
    assert offenders == [], f"CORS support found in: {offenders}"


def test_content_security_policy_is_strict(client: TestClient) -> None:
    csp = client.get("/api/health").headers["content-security-policy"]

    assert "default-src 'none'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'none'" in csp
    assert "form-action 'none'" in csp
    assert "connect-src 'self'" in csp

    # Script execution must never be loosened.
    assert "unsafe-eval" not in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    # No remote origin of any kind is permitted.
    assert "http://" not in csp
    assert "https://" not in csp


def test_style_policy_allows_no_blanket_inline(client: TestClient) -> None:
    """Styles are the one relaxed area, and it is relaxed precisely (IMP-106).

    Inline style *attributes* are allowed, because React Aria positions
    overlays that way. Inline style *elements* are blocked except one exact
    hashed stylesheet that React Aria injects for touch handling.
    """
    csp = client.get("/api/health").headers["content-security-policy"]

    assert "style-src 'self'" in csp
    assert "style-src-attr 'unsafe-inline'" in csp

    # The element-level policy must never become a blanket allowance.
    assert "style-src 'self' 'unsafe-inline'" not in csp
    assert "'sha256-" in csp


def test_react_aria_inline_stylesheet_is_allowed_by_hash(client: TestClient) -> None:
    """Pinned so a HeroUI upgrade that changes the stylesheet is noticed.

    If this fails after an upgrade, load the app in a browser, read the hash
    the console reports, and update REACT_ARIA_PRESSABLE_STYLE_HASH.
    """
    from station_api.security.middleware import REACT_ARIA_PRESSABLE_STYLE_HASH

    csp = client.get("/api/health").headers["content-security-policy"]
    assert REACT_ARIA_PRESSABLE_STYLE_HASH in csp


def test_referrer_policy(client: TestClient) -> None:
    assert client.get("/api/health").headers["referrer-policy"] == "no-referrer"


def test_content_type_options_nosniff(client: TestClient) -> None:
    assert client.get("/api/health").headers["x-content-type-options"] == "nosniff"


def test_framing_is_blocked(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_permissions_policy_disables_capabilities(client: TestClient) -> None:
    policy = client.get("/api/health").headers["permissions-policy"]
    for capability in ("camera", "microphone", "geolocation", "usb", "payment", "serial"):
        assert f"{capability}=()" in policy


def test_cross_origin_isolation_headers(client: TestClient) -> None:
    headers = client.get("/api/health").headers
    assert headers["cross-origin-opener-policy"] == "same-origin"
    assert headers["cross-origin-resource-policy"] == "same-origin"


def test_no_store_on_session_and_bootstrap(
    client: TestClient, app: FastAPI, csrf_token: str
) -> None:
    assert csrf_token
    bootstrap = client.get("/api/session/bootstrap")
    assert bootstrap.headers["cache-control"] == "no-store"

    token = app.state.bootstrap_tokens.issue()
    handoff = client.get(f"/session/{token}", follow_redirects=False)
    assert handoff.headers["cache-control"] == "no-store"

    assert client.get("/api/app/status").headers["cache-control"] == "no-store"


def test_security_headers_present_on_error_responses(client: TestClient) -> None:
    """A 421 or 403 must be as hardened as a 200."""
    for response in (
        client.get("/api/health", headers={"Host": "evil.example"}),
        client.get("/api/health", headers={"Origin": "http://evil.example"}),
        client.get("/api/app/status"),
    ):
        assert "content-security-policy" in response.headers
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"


def test_no_remote_asset_hosts_in_headers(client: TestClient) -> None:
    """No Google Fonts, no CDN - anywhere in the policy surface."""
    headers = client.get("/api/health").headers
    joined = " ".join(f"{key}: {value}" for key, value in headers.items())
    for host in ("googleapis", "gstatic", "cdn.", "unpkg", "jsdelivr"):
        assert host not in joined
