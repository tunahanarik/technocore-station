"""The closed registry of OpenCode Go endpoints, and the closed model table.

This module is the entire outbound surface of the OpenCode connection, in the
same sense :mod:`station_api.technocore.sources` is Technocore's: the client
takes an :class:`OpenCodeEndpoint` from the tuple below and never a URL, so
there is no code path from a request body, a database row or a *catalog
response* to an outbound address.

That last one is the point of this file
---------------------------------------
The model catalog is fetched over the network. A catalog entry that claimed
an endpoint of its own - and JSON that arrives from anywhere can claim
anything - must not be able to steer a request. So the protocol a model
speaks is resolved **here**, from a compile-time table, and the URL is built
from :data:`ENDPOINTS`. Nothing in a fetched document reaches
:func:`station_api.opencode.client.assert_allowed_url`.

What the official documentation established, and what it did not
----------------------------------------------------------------
ADR-0005 1 records the verification, and the split matters enough to repeat
where the code lives:

**Verified** (``opencode.ai/docs/go``, ``/docs/zen``, ``/docs/providers``,
``/docs/config`` and an unauthenticated ``GET /zen/go/v1/models``, read on
4 September 2026; the ``docs/go`` footer carries "Last updated: Sep 3,
2026"):

* the three protocol paths and the models path below, byte for byte;
* the base URL ``https://opencode.ai/zen/go/v1``;
* **which protocol family each published model speaks.** The "Endpoints"
  table has ``Model | Model ID | Endpoint | AI SDK Package`` columns and
  prints an endpoint on every one of its 27 rows, so :data:`MODEL_MAPPINGS`
  below is a transcription of that table and not an inference from it;
* the per-model data terms in the "Privacy" table
  (``Model | Model training | Data retention``), which is why ``retention``
  and ``training_use`` are carried **per row** rather than as one blanket
  sentence;
* that the catalog answers **without a key**, so fetching it proves nothing
  about whether a key is valid;
* that the catalog carries only ``{id, object, created, owned_by}`` - no
  protocol mapping, no context limit, no tool support, no display name and
  no data-retention term - and that on the day it was read it returned
  **34** ids where the documented table has 27. The surplus is exactly what
  ``UNVERIFIED`` is for: listed, and not addressable. That count is a
  measurement with a date on it, not a property of the service: a later read
  returned 35, which is why :data:`EXPECTED_UNMAPPED_COUNT` is pinned and
  :func:`catalog_drift_notice` says so out loud when the catalog outgrows
  it;
* that ``opencode-go/<id>`` is a **provider prefix** and the wire id is the
  bare id;
* that the client is asked to send ``x-opencode-session`` and not to use a
  broad user agent.

**Not found, and therefore not invented:** the request/response shape of the
three families, the streaming and tool-call formats, the error bodies, and
**the name of the authentication header** - ADR-0005 3 has not moved, and
the caveat on it stays.

A correction worth keeping visible
----------------------------------
An earlier revision of this module stated that the documentation
"distinguishes the three families only by an 'AI SDK Package' column and
never says which family a given model belongs to". **That was false.** The
Endpoints table publishes the endpoint per model, and one row here even had
``grok-4.6`` on ``chat/completions`` where the page says ``responses``.

The consequence was not a cosmetic one: with no row marked ``DOCUMENTED``,
:func:`selectable_model_ids` returned the empty set, no model could be
chosen, and the connection was the decorative API box the brief forbids.
The claim is recorded here instead of quietly deleted, because the failure
mode is the interesting part - a cautious-sounding "we could not verify
this" is still a false statement when the source did say it, and it fails
*closed on the feature* while reading like diligence.

Every remaining absence is marked in code rather than papered over. A model
whose protocol is not :data:`MappingVerification.DOCUMENTED` - today that
means a catalog id the Endpoints table does not list - is listed and **not
selectable**, and the reason travels with it to the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

#: The one origin this connection may contact. Scheme, host and the implicit
#: default port 443 are all fixed. There is no setting that changes it, and
#: ``api.opencode.ai`` appears on no documented page (ADR-0005 1).
OPENCODE_ORIGIN = "https://opencode.ai"

#: Exact host expected in the origin. Compared literally, so a sub-domain, a
#: trailing dot, an IP address or user-info cannot match.
OPENCODE_HOST = "opencode.ai"

#: Only the default HTTPS port is acceptable.
OPENCODE_PORT = 443

OPENCODE_SCHEME = "https"

#: The documented base path. Every endpoint below hangs off it.
ZEN_GO_BASE_PATH = "/zen/go/v1"

#: Where a person changes the "Use balance" preference. Shown to the user as
#: text; **never fetched**, and Station does not change any billing setting
#: (ADR-0005 9).
PROVIDER_CONSOLE_URL = "https://opencode.ai/auth"


class Protocol(StrEnum):
    """The three request/response families the service publishes.

    The names come from the documented endpoint paths. What is *not* encoded
    here is any claim about their bodies: ADR-0005 1 records that the shapes
    were not published, and the adapters say the same thing where they parse.
    """

    RESPONSES = "responses"
    MESSAGES = "messages"
    CHAT_COMPLETIONS = "chat_completions"


class EndpointId(StrEnum):
    """Stable identifiers for the four addresses this build knows."""

    MODELS = "models"
    RESPONSES = "responses"
    MESSAGES = "messages"
    CHAT_COMPLETIONS = "chat_completions"


@dataclass(frozen=True, slots=True)
class OpenCodeEndpoint:
    """One address, its fixed path, and how it is treated."""

    id: EndpointId
    path: str
    method: Literal["GET", "POST"]
    #: Whether a provider key is attached. The catalog answers without one,
    #: which is exactly why reading it cannot verify a key (ADR-0005 4).
    requires_key: bool
    #: Whether calling this may cost the user money. Governs retries: a
    #: metered call is attempted **once** (ADR-0005 11).
    metered: bool
    #: Per-endpoint ceiling on the decompressed body, in bytes.
    max_bytes: int
    rationale: str

    @property
    def url(self) -> str:
        """The full, fixed URL. Built here and nowhere else."""
        return f"{OPENCODE_ORIGIN}{self.path}"


#: The complete set. Adding an address means editing this tuple, which is a
#: reviewable change; nothing computes a path at runtime.
ENDPOINTS: tuple[OpenCodeEndpoint, ...] = (
    OpenCodeEndpoint(
        id=EndpointId.MODELS,
        path=f"{ZEN_GO_BASE_PATH}/models",
        method="GET",
        requires_key=False,
        metered=False,
        max_bytes=512 * 1024,
        rationale=(
            "The model catalog. Fetched only when the user asks. It answers "
            "without a key, so a successful fetch says nothing whatever about "
            "whether the stored key is valid."
        ),
    ),
    OpenCodeEndpoint(
        id=EndpointId.RESPONSES,
        path=f"{ZEN_GO_BASE_PATH}/responses",
        method="POST",
        requires_key=True,
        metered=True,
        max_bytes=4 * 1024 * 1024,
        rationale="One of the three published protocol families. Non-streaming only.",
    ),
    OpenCodeEndpoint(
        id=EndpointId.MESSAGES,
        path=f"{ZEN_GO_BASE_PATH}/messages",
        method="POST",
        requires_key=True,
        metered=True,
        max_bytes=4 * 1024 * 1024,
        rationale="One of the three published protocol families. Non-streaming only.",
    ),
    OpenCodeEndpoint(
        id=EndpointId.CHAT_COMPLETIONS,
        path=f"{ZEN_GO_BASE_PATH}/chat/completions",
        method="POST",
        requires_key=True,
        metered=True,
        max_bytes=4 * 1024 * 1024,
        rationale="One of the three published protocol families. Non-streaming only.",
    ),
)

_ENDPOINTS_BY_ID: dict[EndpointId, OpenCodeEndpoint] = {
    endpoint.id: endpoint for endpoint in ENDPOINTS
}

#: Which endpoint each protocol family is spoken on. A closed mapping, so a
#: protocol value can never resolve to an address that is not in ``ENDPOINTS``.
_ENDPOINT_FOR_PROTOCOL: dict[Protocol, EndpointId] = {
    Protocol.RESPONSES: EndpointId.RESPONSES,
    Protocol.MESSAGES: EndpointId.MESSAGES,
    Protocol.CHAT_COMPLETIONS: EndpointId.CHAT_COMPLETIONS,
}


def get_endpoint(endpoint_id: EndpointId) -> OpenCodeEndpoint:
    """Look up an endpoint. Raises ``KeyError`` for anything not registered."""
    return _ENDPOINTS_BY_ID[endpoint_id]


def protocol_endpoint(protocol: Protocol) -> OpenCodeEndpoint:
    """The address one protocol family is spoken on."""
    return _ENDPOINTS_BY_ID[_ENDPOINT_FOR_PROTOCOL[protocol]]


# ---------------------------------------------------------------------------
# Model identifiers
# ---------------------------------------------------------------------------

#: ``opencode-go/`` is a **provider prefix** used in configuration files. It is
#: not part of the wire identifier: the catalog returns bare ids and the bare
#: id is what goes into a request body (ADR-0005 1). Pinned by a test, because
#: sending the prefixed form would be a request for a model that does not
#: exist and the failure would look like a catalog problem.
PROVIDER_PREFIX: Final = "opencode-go/"


def wire_model_id(identifier: str) -> str:
    """The identifier as it goes onto the wire: bare, never prefixed."""
    return identifier.removeprefix(PROVIDER_PREFIX)


class MappingVerification(StrEnum):
    """How the protocol for a model was established.

    ``DOCUMENTED`` means the official documentation named the family for that
    model. ``UNVERIFIED`` means it did not, and the model is therefore listed
    and not selectable - the state ADR-0005 5 requires for anything we would
    otherwise have had to guess.
    """

    DOCUMENTED = "documented"
    UNVERIFIED = "unverified"


class TrainingUse(StrEnum):
    """Whether the provider's privacy table says a model's data trains it.

    ``UNKNOWN`` is not a synonym for ``NO``. A model whose term we could not
    read is treated like a training model for the purpose of asking for
    acknowledgement, and is never described to the user as "not retained"
    (ADR-0005 5).
    """

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ModelMapping:
    """What this build knows about one model, and how it came to know it."""

    wire_id: str
    protocol: Protocol
    protocol_verification: MappingVerification
    #: The provider's published retention term, verbatim-ish and bounded, or
    #: ``"unknown"``. Never rewritten into a reassurance.
    retention: str
    training_use: TrainingUse
    #: Where the privacy term was read and when. Shown beside the term, so a
    #: stale claim is visibly stale rather than silently authoritative.
    privacy_source: str
    privacy_read_on: str
    note: str

    @property
    def selectable(self) -> bool:
        """Only a documented protocol makes a model addressable."""
        return self.protocol_verification is MappingVerification.DOCUMENTED

    @property
    def requires_training_acknowledgement(self) -> bool:
        """``YES`` and ``UNKNOWN`` both ask; only a documented ``NO`` does not."""
        return self.training_use is not TrainingUse.NO


#: Model families the privacy table names as used for training. The **family
#: name** is documented; the exact wire ids are not, so this matches on a
#: normalised prefix and the match is deliberately one-directional: a hit
#: raises the bar (an extra acknowledgement), a miss leaves the term
#: ``UNKNOWN`` rather than declaring it safe. There is no spelling of this
#: constant that can turn an unknown term into "not retained".
TRAINING_FAMILY_PREFIXES: tuple[str, ...] = ("muse-spark",)

#: When both documentation tables were read. Carried into every view so the
#: age of the claim is visible (ADR-0005 5).
PRIVACY_TABLE_READ_ON = "2026-09-04"

PRIVACY_TABLE_SOURCE = "opencode.ai/docs/go - Privacy table"

#: Where the protocol column was read. Named separately from the privacy
#: table because they are two tables on one page and a future edit may move
#: one without the other.
ENDPOINTS_TABLE_SOURCE = "opencode.ai/docs/go - Endpoints table"

#: The date the source page carries in its own footer, which is **not** the
#: date we read it. Both are kept: a page read today can still be a page that
#: stopped being updated a year ago, and only one of the two dates would say
#: so.
DOC_LAST_UPDATED = "2026-09-03"

# --- retention terms, in the provider's words ------------------------------
#
# Kept as the Privacy table prints them rather than translated into a
# reassurance. "0 days" is the provider's claim, not ours, and the difference
# is the whole reason ``privacy_source`` and ``privacy_read_on`` ride along.

RETENTION_ZERO = "0 days"

#: ``deepseek-*`` rows carry an asterisk in the published table and the
#: footnote it points at was not read. Dropping the marker would turn a
#: qualified term into an unqualified one, which is the exact shape of
#: over-claim this module exists to avoid - so the character stays.
RETENTION_ZERO_FOOTNOTED = "0 days*"

RETENTION_THIRTY = "30 days"

#: What the table prints for the two Muse Spark rows. Not a duration: it says
#: the model is outside zero-data-retention altogether.
RETENTION_NOT_ZDR = "Not ZDR"

_NOTE_DOCUMENTED = (
    "Protokol ailesi resmi belgenin 'Endpoints' tablosunda satir satir "
    "yaziyor. Veri saklama kosulu 'Privacy' tablosundan alindi."
)

_NOTE_THIRTY_DAYS = (
    "Protokol ailesi 'Endpoints' tablosunda yaziyor. 'Privacy' tablosu bu "
    "model icin 30 gunluk saklama suresi bildiriyor; sifir degil."
)

_NOTE_FOOTNOTED = (
    "Protokol ailesi 'Endpoints' tablosunda yaziyor. 'Privacy' tablosu "
    "saklama suresini '0 days*' diye yaziyor; yildizin isaret ettigi dipnot "
    "okunmadi, bu yuzden kosulsuz bir sifir gibi gosterilmiyor."
)

_NOTE_TRAINING = (
    "Protokol ailesi 'Endpoints' tablosunda yaziyor. 'Privacy' tablosu bu "
    "modelin verisinin egitim icin kullanildigini ve ZDR kapsaminda "
    "olmadigini soyluyor. Varsayilan olarak secilmez; secmek icin ayrica "
    "onay vermeniz gerekir."
)


def _documented(
    wire_id: str,
    protocol: Protocol,
    *,
    retention: str = RETENTION_ZERO,
    training_use: TrainingUse = TrainingUse.NO,
    note: str = _NOTE_DOCUMENTED,
) -> ModelMapping:
    """One transcribed row of the published table.

    A helper rather than 27 repeated literals, so the table below stays
    scannable against the source page - the property a reviewer actually
    needs to check. It widens nothing: ``protocol`` is a closed enum whose
    every member resolves through :data:`ENDPOINTS`, and the verification
    level is not a parameter, because this function is only ever the
    documented case.
    """
    return ModelMapping(
        wire_id=wire_id,
        protocol=protocol,
        protocol_verification=MappingVerification.DOCUMENTED,
        retention=retention,
        training_use=training_use,
        privacy_source=PRIVACY_TABLE_SOURCE,
        privacy_read_on=PRIVACY_TABLE_READ_ON,
        note=note,
    )


#: The compile-time protocol table: the 27 rows of the "Endpoints" table,
#: joined to the same page's "Privacy" table.
#:
#: This is a **transcription**, which is why every row is ``DOCUMENTED``. The
#: page gives ``Model | Model ID | Endpoint | AI SDK Package`` per row, so
#: nothing here is inferred from the SDK column or from a family resemblance
#: in a model's name.
#:
#: What is deliberately *not* here is the other seven ids the live catalog
#: returned. Writing them would mean guessing a family for a model the page
#: does not list, and a guess would fail the way this module is built to
#: prevent: a request sent to the wrong family comes back as a provider error
#: that reads like the user's mistake. They stay off the table, get
#: :data:`UNMAPPED_REASON` attached, and are listed but not selectable.
#:
#: Order follows the source page, family by family, so a diff against a later
#: revision of the documentation reads as a diff.
MODEL_MAPPINGS: tuple[ModelMapping, ...] = (
    # --- responses (@ai-sdk/openai) ---------------------------------------
    _documented(
        "grok-4.6",
        Protocol.RESPONSES,
        retention=RETENTION_THIRTY,
        note=_NOTE_THIRTY_DAYS,
    ),
    _documented(
        "gpt-5.6-luna",
        Protocol.RESPONSES,
        retention=RETENTION_THIRTY,
        note=_NOTE_THIRTY_DAYS,
    ),
    _documented(
        "muse-spark-1.3-contributor",
        Protocol.RESPONSES,
        retention=RETENTION_NOT_ZDR,
        training_use=TrainingUse.YES,
        note=_NOTE_TRAINING,
    ),
    _documented(
        "muse-spark-1.2-contributor",
        Protocol.RESPONSES,
        retention=RETENTION_NOT_ZDR,
        training_use=TrainingUse.YES,
        note=_NOTE_TRAINING,
    ),
    # --- messages (@ai-sdk/anthropic) -------------------------------------
    _documented("minimax-m3", Protocol.MESSAGES),
    _documented("minimax-m2.7", Protocol.MESSAGES),
    _documented("minimax-m2.5", Protocol.MESSAGES),
    _documented("qwen3.8-max", Protocol.MESSAGES),
    _documented("qwen3.8-flash", Protocol.MESSAGES),
    _documented("qwen3.7-max", Protocol.MESSAGES),
    _documented("qwen3.7-plus", Protocol.MESSAGES),
    _documented("qwen3.6-plus", Protocol.MESSAGES),
    # --- chat/completions (@ai-sdk/openai-compatible) ---------------------
    _documented("glm-5.3-flash", Protocol.CHAT_COMPLETIONS),
    _documented("glm-5.3", Protocol.CHAT_COMPLETIONS),
    _documented("glm-5.2", Protocol.CHAT_COMPLETIONS),
    _documented("glm-5.1", Protocol.CHAT_COMPLETIONS),
    _documented("kimi-k3", Protocol.CHAT_COMPLETIONS),
    _documented("kimi-k2.7-code", Protocol.CHAT_COMPLETIONS),
    _documented("kimi-k2.6", Protocol.CHAT_COMPLETIONS),
    _documented("longcat-2.0", Protocol.CHAT_COMPLETIONS),
    _documented(
        "deepseek-v4-pro",
        Protocol.CHAT_COMPLETIONS,
        retention=RETENTION_ZERO_FOOTNOTED,
        note=_NOTE_FOOTNOTED,
    ),
    _documented(
        "deepseek-v4-flash",
        Protocol.CHAT_COMPLETIONS,
        retention=RETENTION_ZERO_FOOTNOTED,
        note=_NOTE_FOOTNOTED,
    ),
    _documented(
        "deepseek-v4-flash-vision-exp",
        Protocol.CHAT_COMPLETIONS,
        retention=RETENTION_ZERO_FOOTNOTED,
        note=_NOTE_FOOTNOTED,
    ),
    _documented("mimo-v2.5", Protocol.CHAT_COMPLETIONS),
    _documented("mimo-v2.5-pro", Protocol.CHAT_COMPLETIONS),
    _documented("hy4-preview", Protocol.CHAT_COMPLETIONS),
    _documented("hy3", Protocol.CHAT_COMPLETIONS),
)

_MAPPINGS_BY_ID: dict[str, ModelMapping] = {
    mapping.wire_id: mapping for mapping in MODEL_MAPPINGS
}

#: The sentence shown beside a catalog id :data:`MODEL_MAPPINGS` does not
#: list. Turkish and diacritic-free, like every other user-visible string in
#: this codebase.
#:
#: The wording is deliberate and was corrected once. It used to say "this
#: model is not in the official documentation's endpoint table", which is a
#: claim about **the source page as it is right now** - and this process has
#: not read that page since it was built. A review caught the sentence
#: telling a user something false: the live page had gained a row for a model
#: the table below still calls unlisted. What this build can honestly say is
#: what is in *its own pinned table*, and when that table was read.
UNMAPPED_REASON = (
    "Bu model, bu surumun pinli uc nokta tablosunda yok (tablo "
    f"{PRIVACY_TABLE_READ_ON} tarihinde okundu). Konustugu protokol ailesi "
    "bu yuzden dogrulanmadi; listeleniyor ama secilemez. Listelenmek bu "
    "hesabin onu cagirabildigi anlamina da gelmez."
)

#: The sentence shown when the entry exists but its family was not published.
#: No row in :data:`MODEL_MAPPINGS` is in that state today; the path is kept
#: and driven by a test that can reach *only* it (an injected row whose data
#: term is a documented ``no``, so the acknowledgement gate cannot stand in
#: for the protocol gate), because it is where a future id lands if the page
#: adds a model to one table and not the other.
#:
#: Scoped to this build for the same reason as :data:`UNMAPPED_REASON`.
UNVERIFIED_REASON = (
    "Bu modelin protokol ailesi, bu surumun pinli tablosunda bos (tablo "
    f"{PRIVACY_TABLE_READ_ON} tarihinde okundu). Tahmin edilmedi; secilemez."
)

#: How many catalog ids the pinned table did **not** list on the day it was
#: transcribed: the live catalog answered 34 ids, the Endpoints table had 27
#: rows (ADR-0005 1).
#:
#: Written out rather than derived, and this is the whole point. A number
#: computed from the catalog would agree with whatever the catalog said next,
#: which is how the table quietly went stale in the first place: the pinned
#: transcription is dated 3 September and the source page's own footer has
#: since moved on, so a later read returned ids nothing here has ever seen.
#: Pinning the expected surplus turns that from an invisible drift into a
#: sentence the user is shown.
EXPECTED_UNMAPPED_COUNT: Final = 7

#: Always shown beside the model list, whatever the catalog said. Not
#: conditional on anything: the table's age is a fact about every reading of
#: it, and a provenance line that only appears when something else goes wrong
#: is a provenance line nobody ever sees.
TABLE_PROVENANCE = (
    f"Protokol eslemesi bu surumde sabit: {len(MODEL_MAPPINGS)} satirlik "
    f"tablo {PRIVACY_TABLE_READ_ON} tarihinde okundu ve kaynak sayfanin o "
    f"gunku altbilgisi '{DOC_LAST_UPDATED}' diyordu. Kaynak o tarihten sonra "
    "degismis olabilir; Station sayfayi kendiliginden yeniden okumaz."
)


def catalog_drift_notice(*, listed_count: int, unmapped_count: int) -> str:
    """A visible warning when the fetched catalog outgrew the pinned table.

    Empty while the two agree. Non-empty the moment the provider lists more
    ids than the transcription accounted for, which is the earliest signal
    available without re-reading the page - and the signal that was missing
    when a review found the live catalog had grown from 34 ids to 35 while
    :data:`MODEL_MAPPINGS` stayed at its 27 rows and nothing said a word.

    It is a *notice*, not a refusal. The surplus models were already listed
    and unselectable; what changes is that the user is told the table itself
    may be behind, instead of being left to infer it from a list of models
    with no protocol.
    """
    if listed_count <= 0 or unmapped_count <= EXPECTED_UNMAPPED_COUNT:
        return ""
    return (
        f"Saglayicinin katalogu {listed_count} model listeledi ve bunlarin "
        f"{unmapped_count} tanesi bu surumun pinli tablosunda yok. Tablo "
        f"{PRIVACY_TABLE_READ_ON} tarihinde okundugunda fazlalik "
        f"{EXPECTED_UNMAPPED_COUNT} idi. Kaynak sayfa buyumus gorunuyor: "
        "tablo bayat olabilir. Eslemesi olmayan modeller secilemez, tahmin "
        "de edilmez."
    )


def find_mapping(
    identifier: str, *, mappings: tuple[ModelMapping, ...] | None = None
) -> ModelMapping | None:
    """The table entry for a catalog id, or ``None`` when there is none.

    ``mappings`` is a test seam in the same sense the clients' ``transport``
    is: it cannot widen anything. :class:`Protocol` is a closed enum and every
    protocol resolves through :data:`ENDPOINTS`, so an injected table can
    still only produce one of four fixed addresses.
    """
    table = _MAPPINGS_BY_ID if mappings is None else {m.wire_id: m for m in mappings}
    return table.get(wire_model_id(identifier))


def looks_like_a_training_family(identifier: str) -> bool:
    """Whether a catalog id falls in a family the privacy table names.

    Conservative by construction: used only to *raise* the bar for an id with
    no table entry, never to lower it.
    """
    bare = wire_model_id(identifier).strip().lower()
    return any(bare.startswith(prefix) for prefix in TRAINING_FAMILY_PREFIXES)


def selectable_model_ids(
    *, mappings: tuple[ModelMapping, ...] | None = None
) -> frozenset[str]:
    """Every model this build can actually address.

    The 27 transcribed rows, today. It was empty for one revision - the one
    that mis-recorded the documentation as silent about protocol families -
    and an empty return here is what turns the whole connection into a box
    that stores a key and can never use it, so a test asserts the count
    rather than merely that the set is non-empty.
    """
    table = MODEL_MAPPINGS if mappings is None else mappings
    return frozenset(mapping.wire_id for mapping in table if mapping.selectable)


__all__ = [
    "DOC_LAST_UPDATED",
    "ENDPOINTS",
    "EXPECTED_UNMAPPED_COUNT",
    "MODEL_MAPPINGS",
    "OPENCODE_HOST",
    "OPENCODE_ORIGIN",
    "OPENCODE_PORT",
    "OPENCODE_SCHEME",
    "PRIVACY_TABLE_READ_ON",
    "PRIVACY_TABLE_SOURCE",
    "PROVIDER_CONSOLE_URL",
    "PROVIDER_PREFIX",
    "TABLE_PROVENANCE",
    "TRAINING_FAMILY_PREFIXES",
    "UNMAPPED_REASON",
    "UNVERIFIED_REASON",
    "ZEN_GO_BASE_PATH",
    "EndpointId",
    "MappingVerification",
    "ModelMapping",
    "OpenCodeEndpoint",
    "Protocol",
    "TrainingUse",
    "catalog_drift_notice",
    "find_mapping",
    "get_endpoint",
    "looks_like_a_training_family",
    "protocol_endpoint",
    "selectable_model_ids",
    "wire_model_id",
]
