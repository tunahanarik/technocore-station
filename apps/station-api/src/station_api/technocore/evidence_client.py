"""The evidence-read client. GET one room's export, scan it, keep a little.

The **third** and last module in Station that makes an outbound request. The
allow-list of modules permitted to import an HTTP client grows from two to
three here, deliberately and visibly (ADR-0003 1): a reviewer who sees that
list change is seeing the only kind of change that adds an outbound surface.

Why not the read-only client
----------------------------
:class:`~station_api.technocore.client.ReadOnlyTechnocoreClient` takes an
``OfficialSource`` and nothing else, and that signature is a security
property: a room name does not fit through it, and widening it so one could
would delete the property for every caller. Its ``fetch(self, source)``
signature is therefore unchanged. This client carries its own ``export(room)``
instead, and puts the room through the **write path's** policy on the way -
including ``DENIED_ROOMS``, so Lobby is not a target here either.

Why not the write client
------------------------
Opposite failure policies again, in the other direction. A read may be
retried; a write may never be. Sharing a module would mean one of the two
inherits the wrong rule, which is the mistake Package D avoided by splitting
them in the first place (IMP-277).

Transport rules
---------------
* TLS verification is always on. ``verify`` is never named here, and the only
  transport the test seam accepts is an ``httpx.MockTransport``, which speaks
  no TLS at all - so there is no verification to switch off (SI-165).
* Redirects are never followed; a 3xx is a failed read.
* Timeouts are explicit on all four phases. The read phase is longer than the
  document client's because a 10 MiB ring legitimately takes longer than a
  manifest, and shorter than forever.
* The body is scanned **as it streams**, under a 12 MiB cap on decompressed
  bytes. Nothing joins the chunks, so the cap bounds the transfer rather than
  the memory: peak memory is the scanner's bounded window.
* No retry loop. A capture runs because a person asked for one, and if it
  fails they can ask again - which is a retry with a human in it, rather than
  three silent requests against a rate limit shared with the write lane.
* Nothing identifying is attached: no cookie, no authorization, no DID.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from station_api.evidence.stream import (
    CHUNK_BYTES,
    MAX_STREAM_BYTES,
    LineMatch,
    ScanResult,
    scan_export_stream,
)
from station_api.technocore.client import USER_AGENT, assert_allowed_url
from station_api.technocore.evidence_targets import (
    EXPORT_METHOD,
    GENERATION_HEADER,
    EvidenceTarget,
    resolve_export_target,
)
from station_api.technocore.projection import safe_display
from station_api.technocore.write_targets import RoomPolicyError

#: Every phase bounded. The read phase is the generous one: a full ring is
#: megabytes, and a capture that gives up mid-scan is a capture that says
#: "truncated" - honest, but useless.
EXPORT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)

#: Longest excerpt kept from a *failed* read's body, for the record.
MAX_ERROR_EXCERPT_CHARS = 512

#: How much of an error body is read before it is excerpted. Small: an error
#: body is a sentence, and this path exists to explain a failure, not to
#: archive one.
MAX_ERROR_BODY_BYTES = 8 * 1024

#: Content codings that mean "nothing was decoded". Compression is accepted
#: here - unlike on the write lane - because a ring is large and public, and
#: the streaming cap already bounds the decompressed side. The header value is
#: recorded so the SHA-256 below is never mistaken for a hash of wire bytes.
_DECODED_NOTE = "govde transfer/content decoding sonrasi baytlar uzerinden hashlendi"


class EvidenceFetchError(Exception):
    """The export could not be read. Safe to show a user."""


@dataclass(frozen=True, slots=True)
class ExportRead:
    """One completed read of one room's export.

    Carries facts, not a verdict. Turning these into one of the six capture
    states is :mod:`station_api.evidence.service`'s job, and keeping the two
    apart is what stops a transport detail from quietly becoming a claim.
    """

    room: str
    url: str
    http_status: int
    #: The room's conversation epoch as published, or ``""`` when absent.
    generation: str
    scan: ScanResult
    fetched_at: datetime
    #: Empty on success. A bounded, swept sentence otherwise.
    failure_detail: str = ""
    hash_note: str = _DECODED_NOTE

    @property
    def ok(self) -> bool:
        return self.http_status == 200 and not self.failure_detail


class EvidenceClient:
    """Reads one room's export, once, and scans it while it arrives.

    ``transport`` is the same narrowed test seam the other two clients carry:
    only an ``httpx.MockTransport`` is accepted, so a real transport built
    with ``verify=False`` cannot be handed in (SI-165). There is no ``url``,
    ``method``, ``headers`` or ``verify`` parameter anywhere on this class.
    """

    def __init__(self, *, transport: httpx.MockTransport | None = None) -> None:
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise TypeError(
                "EvidenceClient accepts only an httpx.MockTransport. The "
                "production path passes none, so httpx's verifying default "
                "stands and no transport-level TLS setting can be injected."
            )
        self._transport = transport

    def export(
        self,
        room: str,
        *,
        markers: frozenset[str],
        match: LineMatch,
        cap: int = MAX_STREAM_BYTES,
    ) -> ExportRead:
        """Read one room's export and scan it for one record.

        ``room`` goes through the write path's policy before it becomes a
        path segment, so an invalid name, an unknown class marker or a denied
        room is refused here rather than requested and refused remotely.
        Never raises for a network condition: a failure is a result, because
        an exception escaping here would be caught upstream as "not
        published", which is a claim no failed read supports.
        """
        try:
            target = resolve_export_target(room, markers=markers)
        except RoomPolicyError as exc:
            raise EvidenceFetchError(str(exc)) from exc

        return self._read(target, match=match, cap=cap)

    # --- internals ---------------------------------------------------------

    def _read(
        self, target: EvidenceTarget, *, match: LineMatch, cap: int
    ) -> ExportRead:
        url = target.url
        assert_allowed_url(url)
        fetched_at = datetime.now(UTC)

        try:
            with (
                self._client() as client,
                client.stream(EXPORT_METHOD, url) as response,
            ):
                status_code = response.status_code
                if response.is_redirect:
                    # The Location value is attacker-influenced input we have
                    # decided not to act on, so it is not read or recorded.
                    return _failed(
                        target,
                        url,
                        status_code,
                        fetched_at,
                        f"Sunucu {status_code} ile yonlendirdi; yonlendirme izlenmez.",
                    )
                if status_code != httpx.codes.OK:
                    return _failed(
                        target,
                        url,
                        status_code,
                        fetched_at,
                        f"Sunucu {status_code} dondu: "
                        + _error_excerpt(response),
                    )

                generation = _generation(response)
                scan = scan_export_stream(
                    response.iter_bytes(CHUNK_BYTES), match=match, cap=cap
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            return _failed(
                target,
                url,
                0,
                fetched_at,
                f"Disa aktarim okunamadi ({type(exc).__name__}).",
            )

        return ExportRead(
            room=target.room,
            url=url,
            http_status=status_code,
            generation=generation,
            scan=scan,
            fetched_at=fetched_at,
        )

    def _client(self) -> httpx.Client:
        """A client with the security posture fixed in one place.

        ``verify`` is absent on purpose: httpx verifies by default, and not
        naming the parameter means there is no line to flip to ``False``.
        """
        return httpx.Client(
            timeout=EXPORT_TIMEOUT,
            follow_redirects=False,
            transport=self._transport,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/x-ndjson",
                # Compression is accepted here. The cap is enforced on
                # decompressed bytes while streaming, so an expansion bomb
                # ends as ``stream_truncated`` rather than as memory.
                "Accept-Encoding": "gzip, deflate",
            },
            cookies=None,
        )


def _failed(
    target: EvidenceTarget,
    url: str,
    status_code: int,
    fetched_at: datetime,
    detail: str,
) -> ExportRead:
    return ExportRead(
        room=target.room,
        url=url,
        http_status=status_code,
        generation="",
        scan=ScanResult(line=None, line_offset=None),
        fetched_at=fetched_at,
        failure_detail=safe_display(detail),
    )


def _generation(response: httpx.Response) -> str:
    """The room epoch header, kept as digits and nothing else.

    Not parsed into an ``int``: it is compared for equality against a value
    recorded earlier, and a value that only ever round-trips as text cannot
    acquire a rounding error on the way. A header that is not plain digits is
    dropped rather than guessed at - an unreadable generation is a missing
    one, and a missing one makes the capture incomparable rather than equal.
    """
    raw = response.headers.get(GENERATION_HEADER, "").strip()
    return raw if raw.isdigit() and len(raw) <= 32 else ""


def _error_excerpt(response: httpx.Response) -> str:
    """A bounded, swept sentence from an error body.

    Read under its own small cap and never joined into anything larger: this
    is a failure path, and a failure path that buffers a hostile body is a
    second bug waiting for the first one.
    """
    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in response.iter_bytes(CHUNK_BYTES):
            chunks.append(chunk)
            total += len(chunk)
            if total >= MAX_ERROR_BODY_BYTES:
                break
    except (httpx.TimeoutException, httpx.TransportError):
        return "(yanit govdesi okunamadi)"
    body = b"".join(chunks)[:MAX_ERROR_BODY_BYTES]
    if not body:
        return "(bos yanit)"
    text = body.decode("utf-8", errors="replace")
    return safe_display(text[: MAX_ERROR_EXCERPT_CHARS * 2])[:MAX_ERROR_EXCERPT_CHARS]


__all__ = [
    "EXPORT_TIMEOUT",
    "MAX_ERROR_BODY_BYTES",
    "MAX_ERROR_EXCERPT_CHARS",
    "EvidenceClient",
    "EvidenceFetchError",
    "ExportRead",
]
