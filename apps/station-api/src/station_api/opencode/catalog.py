"""Reading the model catalog, and joining it to the closed table.

The catalog is the only document this connection fetches without a
credential, and it is poor: ADR-0005 1 records that each entry carries
``{id, object, created, owned_by}`` and nothing else - no protocol family, no
context limit, no tool support, no display name and no retention term.

So this module does two separate things and keeps them separate on purpose.

**Reading** turns bytes into :class:`CatalogEntry` values and refuses
anything it cannot read, rather than skipping entries quietly. A catalog that
half-parsed would silently shrink the list, and a shorter list looks exactly
like a provider that removed models.

**Joining** puts each entry beside its :class:`~station_api.opencode.
registry.ModelMapping`, if it has one, and produces a :class:`ModelView`
carrying the entry, whether it can be selected, and *why not* when it cannot.
The catalog never decides any of that: nothing an entry claims reaches an
address, a protocol or a privacy statement.

Two sentences this module will not say
--------------------------------------
* "This model is available to you." Listing is not entitlement, and the
  provider answers the catalog to anyone (ADR-0005 5). The view says listed;
  it never says callable.
* "This model does not retain your data." An unknown or unread term stays
  ``unknown`` and asks for acknowledgement. There is no code path from
  "we could not find the term" to a reassurance.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from station_api.opencode.client import RawResponse
from station_api.opencode.errors import OpenCodeResponseError
from station_api.opencode.registry import (
    UNMAPPED_REASON,
    UNVERIFIED_REASON,
    MappingVerification,
    ModelMapping,
    TrainingUse,
    find_mapping,
    looks_like_a_training_family,
    wire_model_id,
)
from station_api.strict_json import StrictJsonError, loads_strict

#: Ceiling on the parsed catalog document.
MAX_CATALOG_BYTES = 512 * 1024

#: Ceiling on how many entries are kept. The observed catalog held 34; this
#: is generous and finite, so a runaway document cannot become a runaway
#: table write.
MAX_CATALOG_ENTRIES = 500

#: Bound on any single field taken from the document.
MAX_FIELD_CHARS = 128

#: Unicode general categories that render as nothing. ``Cf`` is the one that
#: matters most: a right-to-left override is invisible and reorders the text
#: after it, so an identifier could display as one model's name and be
#: another's.
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Co", "Cs", "Cn"})

#: The sentence attached to a fetched catalog, every time it is shown.
LISTING_CAVEAT = (
    "Bu liste saglayicinin acik katalogudur ve anahtarsiz da yanit verir. "
    "Bir modelin listelenmesi, bu hesabin onu cagirabildigi anlamina "
    "gelmez."
)


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One row of the catalog, as it arrived."""

    model_id: str
    owned_by: str
    #: The provider's own creation stamp, when it sent one. Never invented.
    created: int | None


@dataclass(frozen=True, slots=True)
class ModelView:
    """One catalog row joined to what this build knows about it."""

    model_id: str
    owned_by: str
    selectable: bool
    #: Empty when there is no table entry: an absent protocol is not a
    #: default protocol.
    protocol: str
    protocol_verification: str
    reason: str
    retention: str
    training_use: str
    requires_training_acknowledgement: bool
    privacy_source: str
    privacy_read_on: str


def parse_catalog(raw: RawResponse) -> tuple[CatalogEntry, ...]:
    """Read the catalog document, or refuse it whole."""
    if raw.status_code != 200:
        raise OpenCodeResponseError(
            f"catalog answered {raw.status_code}"
        )
    try:
        document: dict[str, Any] = loads_strict(raw.body, max_bytes=MAX_CATALOG_BYTES)
    except StrictJsonError as exc:
        raise OpenCodeResponseError("catalog document is malformed") from exc

    data = document.get("data")
    if not isinstance(data, list):
        raise OpenCodeResponseError("catalog document carries no model list")
    if len(data) > MAX_CATALOG_ENTRIES:
        raise OpenCodeResponseError(
            f"catalog lists more than {MAX_CATALOG_ENTRIES} models"
        )

    entries: list[CatalogEntry] = []
    seen: set[str] = set()
    for row in data:
        entry = _entry(row)
        if entry.model_id in seen:
            # Two rows claiming one id: we cannot say which one the provider
            # meant, and picking either would be a guess.
            raise OpenCodeResponseError("catalog lists a model identifier twice")
        seen.add(entry.model_id)
        entries.append(entry)
    return tuple(entries)


def _entry(row: Any) -> CatalogEntry:
    if not isinstance(row, dict):
        raise OpenCodeResponseError("catalog entry is not an object")
    identifier = row.get("id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise OpenCodeResponseError("catalog entry carries no identifier")
    if len(identifier) > MAX_FIELD_CHARS:
        raise OpenCodeResponseError("catalog entry identifier is too long")

    owned_by = row.get("owned_by")
    owner = owned_by[:MAX_FIELD_CHARS] if isinstance(owned_by, str) else ""

    created = row.get("created")
    stamp = (
        created
        if isinstance(created, int) and not isinstance(created, bool) and created >= 0
        else None
    )
    return CatalogEntry(
        model_id=_swept(wire_model_id(identifier.strip())),
        owned_by=_swept(owner),
        created=stamp,
    )


def _swept(value: str) -> str:
    """Invisible characters out, length bounded.

    The house rule for any imported string that will later be shown (SI-227,
    SI-194): C0/C1 controls **and** the format category, because a bidi
    override is invisible and reorders everything after it - a model
    identifier that renders as one name and is another is worse than a
    mangled one. Characters are substituted rather than deleted, so one
    character in is still one character out and nothing silently shortens.
    """
    return "".join(
        " " if unicodedata.category(character) in _INVISIBLE_CATEGORIES else character
        for character in value
    )[:MAX_FIELD_CHARS]


def build_views(
    entries: tuple[CatalogEntry, ...],
    *,
    mappings: tuple[ModelMapping, ...] | None = None,
) -> tuple[ModelView, ...]:
    """Join every entry to the closed table and say what can be done with it."""
    return tuple(_view(entry, mappings=mappings) for entry in entries)


def _view(
    entry: CatalogEntry, *, mappings: tuple[ModelMapping, ...] | None
) -> ModelView:
    mapping = find_mapping(entry.model_id, mappings=mappings)

    if mapping is None:
        # No entry: unknown protocol, unknown term. The family-name check can
        # only raise the bar, never lower it.
        suspected_training = looks_like_a_training_family(entry.model_id)
        return ModelView(
            model_id=entry.model_id,
            owned_by=entry.owned_by,
            selectable=False,
            protocol="",
            protocol_verification=MappingVerification.UNVERIFIED.value,
            reason=UNMAPPED_REASON,
            retention="unknown",
            training_use=(
                TrainingUse.YES.value if suspected_training else TrainingUse.UNKNOWN.value
            ),
            requires_training_acknowledgement=True,
            privacy_source="",
            privacy_read_on="",
        )

    reason = "" if mapping.selectable else UNVERIFIED_REASON
    return ModelView(
        model_id=entry.model_id,
        owned_by=entry.owned_by,
        selectable=mapping.selectable,
        protocol=mapping.protocol.value,
        protocol_verification=mapping.protocol_verification.value,
        reason=reason,
        retention=mapping.retention,
        training_use=mapping.training_use.value,
        requires_training_acknowledgement=mapping.requires_training_acknowledgement,
        privacy_source=mapping.privacy_source,
        privacy_read_on=mapping.privacy_read_on,
    )


__all__ = [
    "LISTING_CAVEAT",
    "MAX_CATALOG_BYTES",
    "MAX_CATALOG_ENTRIES",
    "MAX_FIELD_CHARS",
    "CatalogEntry",
    "ModelView",
    "build_views",
    "parse_catalog",
]
