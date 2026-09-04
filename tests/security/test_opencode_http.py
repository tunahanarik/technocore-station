"""The OpenCode HTTP surface: guarded, honest, and with no way back to the key.

Two claims are worth more than the rest of this file put together, so they
are tested from several directions each:

* **no response, on any route, can return the stored credential** - there is
  no field for it, no route that reads it, and no response body that contains
  it after one has been stored;
* **no route reports the connection as verified**, because nothing in this
  build can verify it (ADR-0005 4). Storing a key answers with the same
  document a fresh install answers with, differing only in the fingerprint
  and the state - which reads as "saved, not verified" rather than as a tick.

The usual guards are asserted too. They are middleware, so a route cannot opt
out - but "cannot" is exactly the sort of claim that stops being true when
somebody adds a router in the wrong place.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from station_api.app import create_app
from station_api.config import Settings
from station_api.opencode.client import OpenCodeClient
from station_api.opencode.service import OpenCodeService

from tests.conftest import TEST_ONLY_OPENCODE_CREDENTIAL, TEST_PORT
from tests.security.conftest import collect_route_paths, establish_session
from tests.security.opencode_fixtures import (
    CATALOG_DOCUMENT,
    OBSERVED_MODEL_ID,
    SECOND_OBSERVED_MODEL_ID,
    SELECTABLE_IN_CATALOG,
    SURPLUS_MODEL_ID,
    TRAINING_MODEL_ID,
    catalog_transport,
    never_called_transport,
    refusing_transport,
)

pytestmark = pytest.mark.security

IS_WINDOWS = sys.platform == "win32"

windows_only = pytest.mark.skipif(
    not IS_WINDOWS, reason="storing a credential needs DPAPI, a Windows API"
)

STATUS_PATH = "/api/opencode/status"
CREDENTIAL_PATH = "/api/opencode/credential"
FORGET_PATH = "/api/opencode/credential/forget"
REFRESH_PATH = "/api/opencode/catalog/refresh"
MODEL_PATH = "/api/opencode/model"

STATE_CHANGING = (CREDENTIAL_PATH, FORGET_PATH, REFRESH_PATH, MODEL_PATH)


@pytest.fixture
def mocked_app(settings: Settings, engine: Engine) -> FastAPI:
    """The application with a mock transport behind the connection.

    The catalog route reaches the network, and no automated test may
    (SI-158). Injecting the service here is the same seam the composer's
    ``write_client`` is, and it widens nothing: the address still comes from
    the closed endpoint registry.
    """
    transport, _ = catalog_transport()
    return create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        opencode=OpenCodeService(
            engine=engine,
            data_dir=settings.data_dir,
            client=OpenCodeClient(transport=transport, sleep=lambda _: None),
        ),
    )


@pytest.fixture
def mocked_client(mocked_app: FastAPI, base_url: str):  # type: ignore[no-untyped-def]
    with TestClient(mocked_app, base_url=base_url) as test_client:
        establish_session(test_client, mocked_app)
        yield test_client


def _csrf(test_client: TestClient) -> dict[str, str]:
    token: str = test_client.get("/api/session/bootstrap").json()["csrf_token"]
    return {"X-Station-CSRF": token}


# ---------------------------------------------------------------------------
# The guards
# ---------------------------------------------------------------------------


def test_every_opencode_route_requires_a_session(client: TestClient) -> None:
    """Nothing here answers without one.

    The write routes come back 403 rather than 401 because the CSRF
    middleware sits outside the session dependency and refuses first. Either
    way nothing reached a handler, which is the property; asserting 401
    exactly would have been asserting the middleware order.
    """
    assert client.get(STATUS_PATH).status_code == 401
    for path in STATE_CHANGING:
        assert client.post(path, json={}).status_code in {401, 403}


def test_a_state_changing_call_without_csrf_is_refused(
    mocked_client: TestClient,
) -> None:
    for path in STATE_CHANGING:
        assert mocked_client.post(path, json={}).status_code == 403


def test_no_opencode_route_accepts_a_get_write(mocked_client: TestClient) -> None:
    for path in STATE_CHANGING:
        assert mocked_client.get(path).status_code in {404, 405}


def test_the_status_read_rejects_a_foreign_host_and_a_cross_site_request(
    mocked_client: TestClient,
) -> None:
    assert (
        mocked_client.get(STATUS_PATH, headers={"Host": "evil.example"}).status_code
        == 421
    )
    assert (
        mocked_client.get(
            STATUS_PATH, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )


def test_connection_state_is_never_cacheable(mocked_client: TestClient) -> None:
    response = mocked_client.get(STATUS_PATH)
    assert response.headers["Cache-Control"] == "no-store"


# ---------------------------------------------------------------------------
# What the surface does and does not offer
# ---------------------------------------------------------------------------


def test_the_surface_offers_exactly_five_routes_and_no_completion_lane(
    mocked_app: FastAPI,
) -> None:
    """No send, no run, no probe, and no route that reads the key back.

    A completion route would have made "Station never spends money on its
    own" a claim with a footnote, and a read route would have made the
    credential retrievable by anything that can reach loopback.
    """
    paths = {path for path in collect_route_paths(mocked_app) if "opencode" in path}

    assert paths == {
        STATUS_PATH,
        CREDENTIAL_PATH,
        FORGET_PATH,
        REFRESH_PATH,
        MODEL_PATH,
    }
    for path in paths:
        for forbidden in ("complete", "completion", "send", "run", "probe", "reveal"):
            assert forbidden not in path


def test_the_status_document_has_no_field_that_could_hold_a_credential(
    mocked_client: TestClient,
) -> None:
    payload = mocked_client.get(STATUS_PATH).json()

    flattened = json.dumps(payload).lower()
    for forbidden in ('"api_key"', '"key"', '"credential"', '"token"', '"secret"'):
        assert forbidden not in flattened


def test_the_status_document_leaks_no_filesystem_path(
    mocked_client: TestClient, data_dir: Path
) -> None:
    """SI-36: the envelope's path is in the database and never in a response."""
    body = mocked_client.get(STATUS_PATH).text

    assert str(data_dir) not in body
    for marker in ("C:\\", "/home/", "AppData", "LOCALAPPDATA", "station.sqlite3"):
        assert marker not in body


def test_a_fresh_install_reports_not_configured_and_never_verified(
    mocked_client: TestClient,
) -> None:
    payload = mocked_client.get(STATUS_PATH).json()

    assert payload["configured"] is False
    assert payload["fingerprint_short"] == ""
    assert payload["check"]["state"] == "not_configured"
    assert payload["check"]["reasons"]
    assert "verified" not in json.dumps(payload["check"])


def test_the_status_document_carries_the_unverified_header_caveat(
    mocked_client: TestClient,
) -> None:
    """The assumption is restated to the user, not buried in a comment."""
    payload = mocked_client.get(STATUS_PATH).json()
    assert "dogrulanmamistir" in payload["auth_header_caveat"]


def test_the_spending_context_opens_no_budget_and_claims_nothing_unlimited(
    mocked_client: TestClient,
) -> None:
    spending = mocked_client.get(STATUS_PATH).json()["spending"]

    assert spending["budget_available"] is False
    assert {limit["amount_usd"] for limit in spending["limits"]} == {12, 30, 60}
    rendered = json.dumps(spending).lower()
    for forbidden in ("sinirsiz", "unlimited"):
        assert forbidden not in rendered
    # And it says where the control actually lives, without claiming to have
    # touched it.
    assert "konsol" in spending["use_balance"]
    assert "engelledigini iddia etmez" in spending["use_balance"]


def test_the_protocol_context_states_the_two_deferrals(
    mocked_client: TestClient,
) -> None:
    context = mocked_client.get(STATUS_PATH).json()["protocol_context"]

    assert context["streaming_supported"] is False
    assert context["tool_calls_supported"] is False
    assert len(context["protocols"]) == 3
    assert context["deferral"]
    assert context["shape_provenance"]


# ---------------------------------------------------------------------------
# Storing, forgetting, and the state in between
# ---------------------------------------------------------------------------


@windows_only
def test_storing_a_credential_answers_saved_and_not_verified(
    mocked_client: TestClient,
) -> None:
    """The whole point of ADR-0005 4, at the surface a person actually sees."""
    response = mocked_client.post(
        CREDENTIAL_PATH,
        json={"api_key": TEST_ONLY_OPENCODE_CREDENTIAL},
        headers=_csrf(mocked_client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert len(payload["fingerprint_short"]) == 12
    assert payload["check"]["state"] == "key_saved_unverified"
    assert len(payload["check"]["reasons"]) >= 2
    assert "dogrulanmadi" in payload["check"]["detail"]


@windows_only
def test_no_response_in_the_chain_carries_the_stored_credential(
    mocked_client: TestClient,
) -> None:
    """Stored, then every readable surface searched for it."""
    headers = _csrf(mocked_client)
    stored = mocked_client.post(
        CREDENTIAL_PATH,
        json={"api_key": TEST_ONLY_OPENCODE_CREDENTIAL},
        headers=headers,
    )
    status = mocked_client.get(STATUS_PATH)
    refreshed = mocked_client.post(REFRESH_PATH, headers=_csrf(mocked_client))

    for response in (stored, status, refreshed):
        assert TEST_ONLY_OPENCODE_CREDENTIAL not in response.text
        rendered = " ".join(f"{k}: {v}" for k, v in response.headers.items())
        assert TEST_ONLY_OPENCODE_CREDENTIAL not in rendered


@windows_only
def test_forgetting_a_credential_returns_the_connection_to_not_configured(
    mocked_client: TestClient,
) -> None:
    mocked_client.post(
        CREDENTIAL_PATH,
        json={"api_key": TEST_ONLY_OPENCODE_CREDENTIAL},
        headers=_csrf(mocked_client),
    )
    response = mocked_client.post(FORGET_PATH, headers=_csrf(mocked_client))

    payload = response.json()
    assert payload["configured"] is False
    assert payload["fingerprint_short"] == ""
    assert payload["check"]["state"] == "not_configured"


@windows_only
def test_forgetting_a_credential_leaves_the_public_catalog_alone(
    mocked_client: TestClient,
) -> None:
    """The list was never derived from the key; deleting it would be a
    side effect nobody asked for."""
    mocked_client.post(REFRESH_PATH, headers=_csrf(mocked_client))
    before = mocked_client.get(STATUS_PATH).json()["catalog"]["model_count"]
    assert before > 0

    mocked_client.post(
        CREDENTIAL_PATH,
        json={"api_key": TEST_ONLY_OPENCODE_CREDENTIAL},
        headers=_csrf(mocked_client),
    )
    mocked_client.post(FORGET_PATH, headers=_csrf(mocked_client))

    after = mocked_client.get(STATUS_PATH).json()["catalog"]["model_count"]
    assert after == before


def test_a_credential_too_short_to_redact_is_a_clean_refusal(
    mocked_client: TestClient,
) -> None:
    response = mocked_client.post(
        CREDENTIAL_PATH, json={"api_key": "short"}, headers=_csrf(mocked_client)
    )

    assert response.status_code == 400
    assert "redaksiyon" in response.json()["detail"]


def test_a_request_without_a_credential_field_never_reaches_the_handler(
    mocked_client: TestClient,
) -> None:
    """No default, so an omitted key is a 422 rather than an empty store."""
    response = mocked_client.post(
        CREDENTIAL_PATH, json={}, headers=_csrf(mocked_client)
    )
    assert response.status_code == 422


def test_an_extra_field_in_the_request_is_refused(mocked_client: TestClient) -> None:
    """``extra="forbid"``: a stray value cannot be smuggled into the model."""
    response = mocked_client.post(
        CREDENTIAL_PATH,
        json={"api_key": TEST_ONLY_OPENCODE_CREDENTIAL, "endpoint": "https://evil"},
        headers=_csrf(mocked_client),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# The catalog and the model choice, over HTTP
# ---------------------------------------------------------------------------


def test_a_refresh_lists_every_model_and_marks_which_ones_are_addressable(
    mocked_client: TestClient,
) -> None:
    """Listed and selectable are reported as two separate numbers.

    They are two different facts about a model, and a UI given only one of
    them would have to invent the other. Every row is returned - including
    the ones that cannot be chosen - and each unselectable row carries a
    reason a person can read.
    """
    payload = mocked_client.post(REFRESH_PATH, headers=_csrf(mocked_client)).json()
    catalog = payload["catalog"]

    assert catalog["state"] == "ok"
    assert catalog["model_count"] == len(CATALOG_DOCUMENT["data"])
    assert catalog["selectable_count"] == SELECTABLE_IN_CATALOG
    assert 0 < catalog["selectable_count"] < catalog["model_count"]
    assert catalog["listing_caveat"]

    models = {model["model_id"]: model for model in catalog["models"]}
    assert set(models) == {entry["id"] for entry in CATALOG_DOCUMENT["data"]}

    for model in catalog["models"]:
        if model["selectable"]:
            assert model["protocol"]
            assert model["reason"] == ""
        else:
            assert model["reason"], "an unselectable model must say why"
            assert model["requires_training_acknowledgement"] is True

    # The surplus id is present in the list and refused by it.
    assert models[SURPLUS_MODEL_ID]["selectable"] is False
    assert "secilemez" in models[SURPLUS_MODEL_ID]["reason"]

    # The documented rows are addressable, on the families the page prints.
    assert models[OBSERVED_MODEL_ID]["selectable"] is True
    assert models[OBSERVED_MODEL_ID]["protocol"] == "chat_completions"
    assert models[SECOND_OBSERVED_MODEL_ID]["selectable"] is True
    assert models[SECOND_OBSERVED_MODEL_ID]["protocol"] == "responses"

    # The training row is addressable and still gated.
    assert models[TRAINING_MODEL_ID]["selectable"] is True
    assert models[TRAINING_MODEL_ID]["requires_training_acknowledgement"] is True


def test_a_failed_refresh_is_reported_as_a_state_and_not_as_a_five_hundred(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """"We could not read the list" is a state of the connection."""
    import httpx

    transport, _ = refusing_transport(httpx.ConnectError("simulated"))
    app = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        opencode=OpenCodeService(
            engine=engine,
            data_dir=settings.data_dir,
            client=OpenCodeClient(transport=transport, sleep=lambda _: None),
        ),
    )
    with TestClient(app, base_url=base_url) as test_client:
        establish_session(test_client, app)
        response = test_client.post(REFRESH_PATH, headers=_csrf(test_client))

    assert response.status_code == 200
    assert response.json()["catalog"]["state"] == "fetch_error"


def test_a_documented_model_can_be_chosen_over_http_and_survives_a_reread(
    mocked_client: TestClient,
) -> None:
    """The end-to-end claim: a supported model is actually choosable.

    Asserted through the HTTP surface rather than the service, because the
    thing the brief requires is that a person who has entered a key can pick
    a supported model in the running application - not that a function
    somewhere would have allowed it.
    """
    mocked_client.post(REFRESH_PATH, headers=_csrf(mocked_client))

    response = mocked_client.post(
        MODEL_PATH,
        json={"model_id": OBSERVED_MODEL_ID},
        headers=_csrf(mocked_client),
    )

    assert response.status_code == 200
    assert mocked_client.get(STATUS_PATH).json()["selected_model"] == OBSERVED_MODEL_ID


def test_the_prefixed_form_is_accepted_over_http_and_stored_bare(
    mocked_client: TestClient,
) -> None:
    """``opencode-go/`` is a config prefix; the wire id is the bare one."""
    mocked_client.post(REFRESH_PATH, headers=_csrf(mocked_client))

    response = mocked_client.post(
        MODEL_PATH,
        json={"model_id": f"opencode-go/{SECOND_OBSERVED_MODEL_ID}"},
        headers=_csrf(mocked_client),
    )

    assert response.status_code == 200
    selected = mocked_client.get(STATUS_PATH).json()["selected_model"]
    assert selected == SECOND_OBSERVED_MODEL_ID
    assert "opencode-go/" not in selected


def test_a_training_model_is_refused_over_http_until_it_is_acknowledged(
    mocked_client: TestClient,
) -> None:
    """The extra consent, at the surface a person actually meets.

    ``muse-spark`` is documented, so the refusal cannot be "we do not know
    the protocol" - it has to say the data terms, and it has to be liftable
    by the user rather than by us.
    """
    mocked_client.post(REFRESH_PATH, headers=_csrf(mocked_client))

    refused = mocked_client.post(
        MODEL_PATH,
        json={"model_id": TRAINING_MODEL_ID},
        headers=_csrf(mocked_client),
    )
    assert refused.status_code == 400
    assert "onaylamaniz" in refused.json()["detail"]
    assert mocked_client.get(STATUS_PATH).json()["selected_model"] == ""

    allowed = mocked_client.post(
        MODEL_PATH,
        json={"model_id": TRAINING_MODEL_ID, "training_acknowledged": True},
        headers=_csrf(mocked_client),
    )
    assert allowed.status_code == 200
    assert mocked_client.get(STATUS_PATH).json()["selected_model"] == TRAINING_MODEL_ID


def test_choosing_an_unaddressable_model_is_a_refusal_with_the_reason(
    mocked_client: TestClient,
) -> None:
    """A catalog id the published table does not list is refused, with a why.

    And the acknowledgement flag does not get it through: consenting to data
    terms says nothing about whether the protocol family is known.
    """
    mocked_client.post(REFRESH_PATH, headers=_csrf(mocked_client))

    response = mocked_client.post(
        MODEL_PATH,
        json={"model_id": SURPLUS_MODEL_ID},
        headers=_csrf(mocked_client),
    )

    assert response.status_code == 400
    assert "secilemez" in response.json()["detail"]
    assert mocked_client.get(STATUS_PATH).json()["selected_model"] == ""

    forced = mocked_client.post(
        MODEL_PATH,
        json={"model_id": SURPLUS_MODEL_ID, "training_acknowledged": True},
        headers=_csrf(mocked_client),
    )
    assert forced.status_code == 400
    assert mocked_client.get(STATUS_PATH).json()["selected_model"] == ""


def test_choosing_an_unknown_model_is_refused_and_nothing_is_substituted(
    mocked_client: TestClient,
) -> None:
    response = mocked_client.post(
        MODEL_PATH,
        json={"model_id": "a-model-that-does-not-exist"},
        headers=_csrf(mocked_client),
    )

    assert response.status_code == 400
    assert mocked_client.get(STATUS_PATH).json()["selected_model"] == ""


# ---------------------------------------------------------------------------
# Reading costs nothing
# ---------------------------------------------------------------------------


def test_reading_the_status_makes_no_outbound_request(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """Counted at the transport, not inferred from the code (ADR-0005 9)."""
    transport, recorder = never_called_transport()
    app = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        opencode=OpenCodeService(
            engine=engine,
            data_dir=settings.data_dir,
            client=OpenCodeClient(transport=transport, sleep=lambda _: None),
        ),
    )
    with TestClient(app, base_url=base_url) as test_client:
        establish_session(test_client, app)
        for _ in range(3):
            assert test_client.get(STATUS_PATH).status_code == 200

    assert recorder.count == 0


def test_building_the_application_makes_no_outbound_request(
    settings: Settings, engine: Engine, base_url: str
) -> None:
    """A launch that could cost the user money is the worst possible default."""
    transport, recorder = never_called_transport()
    app = create_app(
        settings=settings,
        port=TEST_PORT,
        engine=engine,
        web_dist=None,
        opencode=OpenCodeService(
            engine=engine,
            data_dir=settings.data_dir,
            client=OpenCodeClient(transport=transport, sleep=lambda _: None),
        ),
    )
    with TestClient(app, base_url=base_url):
        pass

    assert recorder.count == 0
