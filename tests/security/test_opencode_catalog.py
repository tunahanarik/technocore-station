"""The catalog, the closed table, and the sentence "listed is not callable".

The provider's catalog answers to anybody and carries four fields. Almost
everything a person would want to choose a model with - the protocol family,
the context limit, the retention term - is somewhere else, and ADR-0005 5
settles what to do about that: resolve the protocol from a compile-time
table, list what the catalog returned, and make the models we cannot address
**visibly** unselectable rather than quietly absent.

So the tests here are about three separations:

* a fetched document decides nothing - not an address, not a protocol, not a
  privacy claim;
* listing is not entitlement and not addressability - two different
  things, and a model can be the first without being the second;
* an unknown retention term is not a reassurance, and asks for the same
  acknowledgement a known training model does.

The catalog fixture is deliberately mixed: documented rows on two protocol
families, a documented row the privacy table marks as a training model, and
two ids the Endpoints table does not list at all. One fetched document
therefore exercises selectable, selectable-but-gated, and listed-not-callable
in the same pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine
from station_api.config import Settings
from station_api.opencode.catalog import (
    LISTING_CAVEAT,
    MAX_CATALOG_ENTRIES,
    build_views,
    parse_catalog,
)
from station_api.opencode.client import OpenCodeClient
from station_api.opencode.errors import ModelNotSelectableError, OpenCodeResponseError
from station_api.opencode.registry import (
    MODEL_MAPPINGS,
    UNMAPPED_REASON,
    UNVERIFIED_REASON,
    MappingVerification,
    ModelMapping,
    Protocol,
    TrainingUse,
    selectable_model_ids,
)
from station_api.opencode.service import (
    SELECTED_MODEL_KEY,
    CatalogState,
    OpenCodeService,
    VerificationState,
)

from tests.security.opencode_fixtures import (
    CATALOG_DOCUMENT,
    OBSERVED_MODEL_ID,
    SECOND_OBSERVED_MODEL_ID,
    SELECTABLE_IN_CATALOG,
    SURPLUS_MODEL_ID,
    TRAINING_FAMILY_MODEL_ID,
    TRAINING_MODEL_ID,
    catalog_bytes,
    catalog_transport,
    never_called_transport,
    recording_transport,
    refusing_transport,
    status_transport,
)

pytestmark = pytest.mark.security

#: A TEST-ONLY table, injected as a seam exactly as the composer's signer
#: is. It cannot widen anything: ``Protocol`` is a closed enum and every
#: protocol resolves to one of the four registered addresses.
#:
#: The selection tests below run against the **real** table wherever they
#: can, because the real one now has documented rows and proving the
#: mechanism against a fixture would prove less. This stays for the cases
#: that need a shape the real table does not contain - a row that is present
#: and ``unverified``, which is where a future id lands if the page adds a
#: model to one table and not the other.
DOCUMENTED_TABLE: tuple[ModelMapping, ...] = (
    ModelMapping(
        wire_id=OBSERVED_MODEL_ID,
        protocol=Protocol.CHAT_COMPLETIONS,
        protocol_verification=MappingVerification.DOCUMENTED,
        retention="30 gun",
        training_use=TrainingUse.NO,
        privacy_source="TEST-ONLY",
        privacy_read_on="2026-09-04",
        note="TEST-ONLY",
    ),
)

#: One row, present and **not** documented. No row of the real table is in
#: that state today; the path is kept, and kept tested, because it is where a
#: model listed in the Privacy table but missing from the Endpoints table
#: would land.
UNVERIFIED_TABLE: tuple[ModelMapping, ...] = (
    ModelMapping(
        wire_id=OBSERVED_MODEL_ID,
        protocol=Protocol.CHAT_COMPLETIONS,
        protocol_verification=MappingVerification.UNVERIFIED,
        retention="unknown",
        training_use=TrainingUse.UNKNOWN,
        privacy_source="TEST-ONLY",
        privacy_read_on="2026-09-04",
        note="TEST-ONLY",
    ),
)

TRAINING_TABLE: tuple[ModelMapping, ...] = (
    ModelMapping(
        wire_id=TRAINING_FAMILY_MODEL_ID,
        protocol=Protocol.CHAT_COMPLETIONS,
        protocol_verification=MappingVerification.DOCUMENTED,
        retention="egitim icin kullanilir",
        training_use=TrainingUse.YES,
        privacy_source="TEST-ONLY",
        privacy_read_on="2026-09-04",
        note="TEST-ONLY",
    ),
)


def _service(
    engine: Engine,
    settings: Settings,
    *,
    transport: httpx.MockTransport,
    mappings: tuple[ModelMapping, ...] | None = None,
) -> OpenCodeService:
    return OpenCodeService(
        engine=engine,
        data_dir=settings.data_dir,
        client=OpenCodeClient(transport=transport, sleep=lambda _: None),
        mappings=mappings,
    )


def _raw(body: bytes, status_code: int = 200):  # type: ignore[no-untyped-def]
    transport, _ = status_transport(status_code, body=body)
    return OpenCodeClient(transport=transport, sleep=lambda _: None).fetch_catalog()


# ---------------------------------------------------------------------------
# Reading the document
# ---------------------------------------------------------------------------


def test_the_catalog_is_read_as_the_four_fields_it_actually_carries() -> None:
    entries = parse_catalog(_raw(catalog_bytes()))

    assert len(entries) == len(CATALOG_DOCUMENT["data"])
    first = entries[0]
    assert first.model_id == OBSERVED_MODEL_ID
    assert first.owned_by == "opencode"
    assert isinstance(first.created, int)


def test_a_catalog_that_half_parses_is_refused_whole() -> None:
    """Skipping an unreadable row would silently shrink the list.

    A shorter list looks exactly like a provider that removed models, which
    is a conclusion nobody should draw from a parsing bug.
    """
    for hostile in (
        {"object": "list", "data": [{"object": "model"}]},
        {"object": "list", "data": ["not-an-object"]},
        {"object": "list", "data": [{"id": ""}]},
        {"object": "list"},
        {"object": "list", "data": {"id": "x"}},
    ):
        with pytest.raises(OpenCodeResponseError):
            parse_catalog(_raw(json.dumps(hostile).encode()))


def test_a_catalog_that_lists_one_identifier_twice_is_refused() -> None:
    """Two rows claiming one id: picking either would be a guess."""
    document = {
        "object": "list",
        "data": [
            {"id": OBSERVED_MODEL_ID, "owned_by": "a"},
            {"id": OBSERVED_MODEL_ID, "owned_by": "b"},
        ],
    }
    with pytest.raises(OpenCodeResponseError):
        parse_catalog(_raw(json.dumps(document).encode()))


def test_an_unbounded_catalog_is_refused() -> None:
    document = {
        "object": "list",
        "data": [{"id": f"m{index}"} for index in range(MAX_CATALOG_ENTRIES + 1)],
    }
    with pytest.raises(OpenCodeResponseError):
        parse_catalog(_raw(json.dumps(document).encode()))


def test_a_created_stamp_that_is_not_an_integer_becomes_absent_not_zero() -> None:
    document = {"object": "list", "data": [{"id": "m1", "created": "yesterday"}]}
    entries = parse_catalog(_raw(json.dumps(document).encode()))

    assert entries[0].created is None


def test_an_imported_identifier_is_swept_and_bounded() -> None:
    """The house rule for any imported string that will later be shown."""
    document = {"object": "list", "data": [{"id": "m\u0000\u202e1", "owned_by": "x" * 400}]}
    entries = parse_catalog(_raw(json.dumps(document).encode()))

    assert "\u0000" not in entries[0].model_id
    assert "\u202e" not in entries[0].model_id
    assert len(entries[0].owned_by) <= 128


# ---------------------------------------------------------------------------
# Joining to the closed table
# ---------------------------------------------------------------------------


def test_a_model_with_no_table_entry_is_listed_and_not_selectable() -> None:
    entries = parse_catalog(_raw(catalog_bytes()))
    views = {view.model_id: view for view in build_views(entries)}

    unmapped = views[TRAINING_FAMILY_MODEL_ID]
    assert unmapped.selectable is False
    assert unmapped.protocol == ""
    assert unmapped.reason == UNMAPPED_REASON
    assert "secilemez" in unmapped.reason


def test_the_catalog_surplus_is_listed_with_its_reason_and_cannot_be_chosen() -> None:
    """The seven-model gap between the live catalog and the published table.

    ADR-0005 1 recorded 34 ids from the catalog against 27 rows in the
    Endpoints table. The surplus is the whole reason ``UNVERIFIED`` exists:
    the honest answer is to show the model, say plainly why it cannot be
    picked, and guess nothing - not to hide it, which would look like a
    provider that had removed it.
    """
    entries = parse_catalog(_raw(catalog_bytes()))
    views = {view.model_id: view for view in build_views(entries)}

    surplus = views[SURPLUS_MODEL_ID]
    assert surplus.selectable is False
    assert surplus.protocol == ""
    assert surplus.protocol_verification == MappingVerification.UNVERIFIED.value
    assert surplus.reason == UNMAPPED_REASON
    assert "secilemez" in surplus.reason
    # Listed is the other half of the claim: it is still in the document.
    assert SURPLUS_MODEL_ID in views
    # ...and it says nothing reassuring about data it never read a term for.
    assert surplus.retention == "unknown"
    assert surplus.requires_training_acknowledgement is True


def test_a_row_that_is_present_but_unverified_says_so_and_not_something_else() -> None:
    """Two absences, two different sentences.

    "The table has no row for this id" and "the row exists and its family was
    never published" are different facts, and a user who is told the wrong
    one has been told something false about what we checked.
    """
    entries = parse_catalog(_raw(catalog_bytes()))
    views = {
        view.model_id: view
        for view in build_views(entries, mappings=UNVERIFIED_TABLE)
    }

    assert views[OBSERVED_MODEL_ID].selectable is False
    assert views[OBSERVED_MODEL_ID].reason == UNVERIFIED_REASON
    assert views[SURPLUS_MODEL_ID].reason == UNMAPPED_REASON
    assert UNVERIFIED_REASON != UNMAPPED_REASON


def test_a_documented_row_is_listed_as_selectable_with_its_own_protocol() -> None:
    """The corrected table, seen from the catalog side.

    Both documented rows come back selectable, and on the two *different*
    families the page prints for them - which is what proves the protocol is
    read from the table rather than defaulted or inferred from the id.
    """
    entries = parse_catalog(_raw(catalog_bytes()))
    views = {view.model_id: view for view in build_views(entries)}

    first = views[OBSERVED_MODEL_ID]
    assert first.selectable is True
    assert first.protocol == Protocol.CHAT_COMPLETIONS.value
    assert first.protocol_verification == MappingVerification.DOCUMENTED.value
    assert first.reason == ""
    assert first.requires_training_acknowledgement is False

    second = views[SECOND_OBSERVED_MODEL_ID]
    assert second.selectable is True
    assert second.protocol == Protocol.RESPONSES.value
    assert second.retention == "30 days"
    assert first.protocol != second.protocol


def test_this_build_can_address_the_documented_models() -> None:
    """The regression this file exists to keep out.

    An earlier revision recorded that the documentation "never says which
    family a model belongs to" and marked all 27 rows unverified, so this
    set was empty and the dropdown could not be filled at all. The page does
    say; the set is not empty; and it is asserted as a *count* so one
    accidental row cannot satisfy it.
    """
    selectable = selectable_model_ids()

    assert len(selectable) == 27
    assert OBSERVED_MODEL_ID in selectable
    assert SECOND_OBSERVED_MODEL_ID in selectable
    assert all(mapping.selectable for mapping in MODEL_MAPPINGS)


def test_a_documented_row_carries_the_term_the_privacy_table_printed() -> None:
    """Per model, with its provenance - never one blanket sentence.

    A documented ``NO`` is allowed to say so, which is exactly why it has to
    arrive with the source and the date it was read: the claim is the
    provider's, and the view says whose it is.
    """
    entries = parse_catalog(_raw(catalog_bytes()))
    views = {view.model_id: view for view in build_views(entries)}

    documented = views[OBSERVED_MODEL_ID]
    assert documented.training_use == TrainingUse.NO.value
    assert documented.retention == "0 days"
    assert documented.privacy_source
    assert documented.privacy_read_on == "2026-09-04"


def test_an_unknown_retention_term_is_never_shown_as_not_retained() -> None:
    """"We could not read the term" has no path to "your data is not kept".

    Narrowed, not weakened: the rule now bites exactly where it should - on
    the rows with no table entry. A row that *does* have one may report the
    published term, and must carry the source and date that make it the
    provider's claim rather than ours.
    """
    entries = parse_catalog(_raw(catalog_bytes()))
    views = {view.model_id: view for view in build_views(entries)}

    for model_id in (SURPLUS_MODEL_ID, TRAINING_FAMILY_MODEL_ID):
        view = views[model_id]
        assert view.training_use != TrainingUse.NO.value
        assert view.retention == "unknown"
        assert view.requires_training_acknowledgement is True
        # No provenance is offered for a term that was never read.
        assert view.privacy_source == ""
        assert view.privacy_read_on == ""

    for view in build_views(entries):
        if view.training_use == TrainingUse.NO.value:
            assert view.privacy_source, f"{view.model_id} claims a term with no source"
            assert view.privacy_read_on


def test_a_documented_training_model_is_listed_selectable_and_still_gated() -> None:
    """Selectable and "needs acknowledgement" are separate properties.

    Marking a training model unselectable would have been the wrong refusal:
    it would say the family is unknown, which is false. The family is known;
    what is true is that the provider trains on the data, and that is a
    decision for the user to take explicitly (ADR-0005 5).
    """
    entries = parse_catalog(_raw(catalog_bytes()))
    views = {view.model_id: view for view in build_views(entries)}

    training = views[TRAINING_MODEL_ID]
    assert training.selectable is True
    assert training.training_use == TrainingUse.YES.value
    assert training.retention == "Not ZDR"
    assert training.requires_training_acknowledgement is True


def test_a_training_family_identifier_raises_the_bar_and_never_lowers_it() -> None:
    entries = parse_catalog(_raw(catalog_bytes()))
    views = {view.model_id: view for view in build_views(entries)}

    assert views[TRAINING_FAMILY_MODEL_ID].training_use == TrainingUse.YES.value
    assert views[TRAINING_FAMILY_MODEL_ID].requires_training_acknowledgement is True


def test_the_catalog_cannot_make_a_model_selectable() -> None:
    """A fetched document decides nothing (ADR-0005 5).

    The document here claims a protocol, a context window and that it is
    "available". None of those fields exists in the view, and the model is
    still unselectable, because the only thing consulted is the closed table.
    """
    hostile = {
        "object": "list",
        "data": [
            {
                "id": "hostile-TEST-ONLY",
                "owned_by": "x",
                "protocol": "chat_completions",
                "endpoint": "https://evil.example/v1/chat",
                "selectable": True,
                "retention": "not retained",
            }
        ],
    }
    views = build_views(parse_catalog(_raw(json.dumps(hostile).encode())))

    assert views[0].selectable is False
    assert views[0].protocol == ""
    assert views[0].retention == "unknown"


# ---------------------------------------------------------------------------
# The service: fetching only on request, and keeping the cache honest
# ---------------------------------------------------------------------------


def test_building_the_service_and_reading_it_contacts_nobody(
    engine: Engine, settings: Settings
) -> None:
    """Counted, not asserted. A launch that could cost money is the worst default."""
    transport, recorder = never_called_transport()
    service = _service(engine, settings, transport=transport)

    view = service.describe()

    assert recorder.count == 0
    assert view.catalog.state is CatalogState.NEVER_FETCHED
    assert view.catalog.models == ()


def test_a_refresh_fetches_once_and_stores_what_it_read(
    engine: Engine, settings: Settings
) -> None:
    transport, recorder = catalog_transport()
    service = _service(engine, settings, transport=transport)

    view = service.refresh_catalog()

    assert recorder.count == 1
    assert view.state is CatalogState.OK
    assert view.models_fetched_at is not None
    assert {model.model_id for model in view.models} == {
        entry["id"] for entry in CATALOG_DOCUMENT["data"]
    }
    # Listed is not addressable: every row is kept, and only the documented
    # ones are counted as selectable.
    assert len(view.models) > view.selectable_count
    assert view.selectable_count == SELECTABLE_IN_CATALOG


def test_a_failed_refresh_shows_the_error_without_deleting_the_cache(
    engine: Engine, settings: Settings
) -> None:
    """Both facts, separately dated (ADR-0005 5).

    A single timestamp would have forced a choice between hiding the outage
    and throwing away a list the user can still read honestly.
    """
    good, _ = catalog_transport()
    service = _service(engine, settings, transport=good)
    first = service.refresh_catalog()
    assert first.state is CatalogState.OK

    bad, recorder = refusing_transport(httpx.ConnectError("simulated"))
    broken = OpenCodeService(
        engine=engine,
        data_dir=settings.data_dir,
        client=OpenCodeClient(transport=bad, sleep=lambda _: None),
    )
    second = broken.refresh_catalog()

    assert recorder.count >= 1
    assert second.state is CatalogState.FETCH_ERROR
    assert second.detail
    # The list survived, and carries its own date rather than the failure's.
    assert len(second.models) == len(first.models)
    assert second.models_fetched_at == first.models_fetched_at
    assert second.fetched_at is not None
    assert second.fetched_at >= first.fetched_at


def test_a_malformed_document_is_a_parse_error_and_not_an_empty_catalog(
    engine: Engine, settings: Settings
) -> None:
    transport, _ = status_transport(200, body=b'{"object": "list"}')
    service = _service(engine, settings, transport=transport)

    view = service.refresh_catalog()

    assert view.state is CatalogState.PARSE_ERROR
    assert view.detail


def test_a_catalog_read_says_nothing_about_the_credential(
    engine: Engine, settings: Settings
) -> None:
    """The whole reason "check the connection" produces no badge.

    A successful read here is a fact about a public document. The connection
    check must not move because of it.
    """
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)

    before = service.check_connection().state
    service.refresh_catalog()
    after = service.check_connection().state

    assert before is VerificationState.NOT_CONFIGURED
    assert after is VerificationState.NOT_CONFIGURED


def test_repeated_refreshes_do_not_grow_the_cache_without_bound(
    engine: Engine, settings: Settings
) -> None:
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)

    for _ in range(25):
        service.refresh_catalog()

    with engine.connect() as connection:
        checks = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM opencode_catalog_check"
        ).scalar()
    assert checks is not None and checks <= 20


def test_the_listing_caveat_never_promises_entitlement() -> None:
    assert "anlamina" in LISTING_CAVEAT
    assert "gelmez" in LISTING_CAVEAT


# ---------------------------------------------------------------------------
# Choosing a model
# ---------------------------------------------------------------------------


def test_an_unmapped_model_is_refused_and_nothing_is_substituted(
    engine: Engine, settings: Settings
) -> None:
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)
    service.refresh_catalog()

    with pytest.raises(ModelNotSelectableError) as caught:
        service.select_model(TRAINING_FAMILY_MODEL_ID)

    assert "secilemez" in str(caught.value)
    assert service.describe().selected_model == ""


def test_a_model_whose_family_was_never_published_is_refused(
    engine: Engine, settings: Settings
) -> None:
    """The present-but-unverified path, through the injected table.

    No row of the real table is in that state, so the seam is the only way to
    reach this branch - and it has to stay reachable, because it is what a
    future page edit lands on.
    """
    transport, _ = catalog_transport()
    service = _service(
        engine, settings, transport=transport, mappings=UNVERIFIED_TABLE
    )

    with pytest.raises(ModelNotSelectableError) as caught:
        service.select_model(OBSERVED_MODEL_ID)

    assert "secilemez" in str(caught.value)
    assert service.describe().selected_model == ""


def test_a_surplus_model_is_refused_through_the_real_table(
    engine: Engine, settings: Settings
) -> None:
    """A catalog id the Endpoints table does not list is refused, not guessed.

    Run against the **real** table rather than a seam, so the refusal is the
    shipped behaviour and not a property of a fixture.
    """
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)
    service.refresh_catalog()

    with pytest.raises(ModelNotSelectableError) as caught:
        service.select_model(SURPLUS_MODEL_ID)

    assert "secilemez" in str(caught.value)
    assert service.describe().selected_model == ""


def test_a_documented_model_can_be_chosen_and_the_choice_lives_in_the_backend(
    engine: Engine, settings: Settings
) -> None:
    """Against the real table, because the real table now has documented rows.

    This is the assertion that says the connection is a working feature: a
    model the published page names can be chosen, and the choice is kept in
    the backend rather than in the browser.
    """
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)

    chosen = service.select_model(OBSERVED_MODEL_ID)

    assert chosen == OBSERVED_MODEL_ID
    assert service.describe().selected_model == OBSERVED_MODEL_ID

    with engine.connect() as connection:
        stored = connection.exec_driver_sql(
            "SELECT value FROM app_metadata WHERE key = ?", (SELECTED_MODEL_KEY,)
        ).scalar()
    assert stored == OBSERVED_MODEL_ID


def test_a_model_on_each_documented_family_can_be_chosen(
    engine: Engine, settings: Settings
) -> None:
    """One id per family, so no family is documented in name only."""
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)

    for wire_id in ("grok-4.6", "minimax-m3", "glm-5.3"):
        assert service.select_model(wire_id) == wire_id
        assert service.describe().selected_model == wire_id


def test_a_training_model_is_not_selectable_by_default_and_needs_acknowledgement(
    engine: Engine, settings: Settings
) -> None:
    """Against the real table: ``muse-spark`` is documented *and* gated.

    The first call is refused even though the row is ``documented`` and the
    protocol is known, and the refusal names the reason. The second call
    carries the acknowledgement and is allowed - so the gate is a decision
    the user takes, not a model Station quietly avoids.
    """
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)

    with pytest.raises(ModelNotSelectableError) as caught:
        service.select_model(TRAINING_MODEL_ID)
    assert "onaylamaniz" in str(caught.value)
    assert service.describe().selected_model == ""

    assert (
        service.select_model(TRAINING_MODEL_ID, training_acknowledged=True)
        == TRAINING_MODEL_ID
    )
    assert service.describe().selected_model == TRAINING_MODEL_ID


def test_an_acknowledgement_does_not_unlock_an_unaddressable_model(
    engine: Engine, settings: Settings
) -> None:
    """The training gate is not a master key.

    Acknowledging the data terms says something about privacy; it says
    nothing about whether the protocol family is known, so it must not turn
    an unmapped id into a selectable one.
    """
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)

    with pytest.raises(ModelNotSelectableError):
        service.select_model(SURPLUS_MODEL_ID, training_acknowledged=True)
    with pytest.raises(ModelNotSelectableError):
        service.select_model(TRAINING_FAMILY_MODEL_ID, training_acknowledged=True)

    assert service.describe().selected_model == ""


def test_choosing_a_model_sends_nothing(engine: Engine, settings: Settings) -> None:
    transport, recorder = never_called_transport()
    service = _service(engine, settings, transport=transport)

    service.select_model(OBSERVED_MODEL_ID)

    assert recorder.count == 0


def test_the_prefixed_form_resolves_to_the_same_bare_identifier(
    engine: Engine, settings: Settings
) -> None:
    """``opencode-go/`` is a provider prefix, never part of the wire id.

    Sending the prefixed form would be a request for a model that does not
    exist, and the provider's error would read like a catalog problem.
    """
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)

    assert service.select_model(f"opencode-go/{OBSERVED_MODEL_ID}") == OBSERVED_MODEL_ID
    assert service.describe().selected_model == OBSERVED_MODEL_ID


# ---------------------------------------------------------------------------
# Where the cache lives
# ---------------------------------------------------------------------------


def test_the_cache_leaves_no_file_behind_and_no_path_to_leak(
    engine: Engine, settings: Settings, data_dir: Path
) -> None:
    """The catalog cache is a table, not a file (ADR-0005 5, SI-36).

    A cache file would need a path, a path would need to be recorded, and a
    recorded path is the thing SI-36 says must never come back over HTTP.
    Keeping it in the database removes the question.
    """
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)
    service.refresh_catalog()

    stray = [
        path
        for path in data_dir.rglob("*")
        if path.is_file() and "catalog" in path.name.lower()
    ]
    assert stray == []

    with engine.connect() as connection:
        columns = connection.exec_driver_sql(
            "SELECT * FROM opencode_catalog_check LIMIT 1"
        ).keys()
    assert "snapshot_relpath" not in columns
    assert "path" not in columns


def test_the_stored_excerpt_is_bounded(engine: Engine, settings: Settings) -> None:
    padded = dict(CATALOG_DOCUMENT)
    padded["padding"] = "x" * 20000
    transport, _ = recording_transport(
        lambda _: httpx.Response(200, content=catalog_bytes(padded))
    )
    service = _service(engine, settings, transport=transport)
    service.refresh_catalog()

    with engine.connect() as connection:
        excerpt = connection.exec_driver_sql(
            "SELECT snapshot_excerpt FROM opencode_catalog_check"
        ).scalar()
    assert excerpt is not None
    assert len(excerpt) <= 4096


def test_a_successful_read_dates_the_attempt_and_the_list_identically(
    engine: Engine, settings: Settings
) -> None:
    """Age is shown, so an old list is visibly old rather than silently current.

    On a good read the two dates coincide; the failure test above is where
    they come apart, which is the case the second field exists for.
    """
    transport, _ = catalog_transport()
    service = _service(engine, settings, transport=transport)
    view = service.refresh_catalog()

    assert view.models_fetched_at is not None
    assert view.models_fetched_at == view.fetched_at
    assert service.describe().catalog.models_fetched_at == view.models_fetched_at
