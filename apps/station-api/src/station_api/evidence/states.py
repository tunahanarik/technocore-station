"""The six capture states, and why none of them is a green badge.

ADR-0003 3. A capture attempt ends in exactly one of these, and five of the
six establish nothing at all about whether a message was published:

``line_captured``       our record was found; its raw bytes and offset are
                        kept. This is a **level 2 server observation** - the
                        strongest thing a capture can be, and still not proof
                        that the message was sent, because it is one server's
                        answer about its own state.
``line_not_found``      the record was not in the scanned part of the ring.
                        This **proves nothing**: the ring forgets, an ``e-``
                        room forgets faster, and a message that was published
                        and has since rolled out looks exactly like one that
                        was never published.
``generation_changed``  the room's epoch is not the one the earlier capture
                        saw, so the two are **not comparable**.
``stream_truncated``    the scan hit its cap. Absence within a partial scan
                        is absence of a scan, not absence of a record.
``parse_problem``       lines could not be read. Unreadable is not altered
                        (the IMP-238 distinction, applied here).
``fetch_failed``        the read did not complete.

What may and may not be retried
-------------------------------
A capture is a **read**, and a read may be retried - by the user, on request,
as many times as they like. Nothing in this package retries a *write*, offers
to, or hints at it (ADR-0002 3, SI-150). In particular ``line_not_found``
never converts an ``outcome_unknown`` send into ``not_sent``: that conversion
is the single inference this whole model exists to refuse.
"""

from __future__ import annotations

from enum import StrEnum


class CaptureState(StrEnum):
    """How one capture attempt ended."""

    LINE_CAPTURED = "line_captured"
    LINE_NOT_FOUND = "line_not_found"
    GENERATION_CHANGED = "generation_changed"
    STREAM_TRUNCATED = "stream_truncated"
    PARSE_PROBLEM = "parse_problem"
    FETCH_FAILED = "fetch_failed"

    @property
    def is_server_observation(self) -> bool:
        """True only for ``line_captured``, and it means level 2 - no more."""
        return self is CaptureState.LINE_CAPTURED

    @property
    def may_retry_read(self) -> bool:
        """Re-reading is free and changes nothing on the server."""
        return True

    @property
    def may_retry_write(self) -> bool:
        """Never. Not for any state, not under any condition."""
        return False


#: Every state that is *not* a captured line. Named so a caller cannot write
#: ``state != LINE_CAPTURED`` in five places and get one of them backwards.
INCONCLUSIVE_STATES: frozenset[CaptureState] = frozenset(
    state for state in CaptureState if not state.is_server_observation
)

#: One sentence per state, in Turkish, safe to show. None of them claims more
#: than the state establishes, and none uses a forbidden phrase
#: (:mod:`station_api.evidence.language`).
CAPTURE_DETAIL: dict[CaptureState, str] = {
    CaptureState.LINE_CAPTURED: (
        "Kendi kaydimizin disa aktarilan satiri bulundu ve ham baytlariyla "
        "saklandi. Bu bir sunucu gozlemidir (Seviye 2); mesajin yayimlandiginin "
        "bagimsiz bir ispati degildir."
    ),
    CaptureState.LINE_NOT_FOUND: (
        "Taranan kayitlar arasinda kendi satirimiz yoktu. Bu hicbir sey "
        "kanitlamaz: oda halkasi eski kayitlari unutur, bu yuzden 'yayimlanmadi' "
        "sonucu cikarilmaz."
    ),
    CaptureState.GENERATION_CHANGED: (
        "Odanin generation degeri onceki yakalamadakinden farkli. Iki kayit "
        "karsilastirilamaz; bu bir uyusmazlik degil, farkli bir donemdir."
    ),
    CaptureState.STREAM_TRUNCATED: (
        "Disa aktarim akisi tarama tavanina dayandi; tarama tamamlanamadi. "
        "Eksik bir taramada satirin bulunmamasi bir sonuc degildir."
    ),
    CaptureState.PARSE_PROBLEM: (
        "Akistaki bazi satirlar okunamadi. Okunamayan bir satir degistirilmis "
        "bir satir demek degildir; yalnizca degerlendirilemedi."
    ),
    CaptureState.FETCH_FAILED: (
        "Disa aktarim okunamadi. Okuma yeniden denenebilir; gonderim asla "
        "yeniden denenmez."
    ),
}


__all__ = ["CAPTURE_DETAIL", "INCONCLUSIVE_STATES", "CaptureState"]
