"""One reading turn: ask, resolve against the closed registry, return verdicts.

ADR-0014. This is the whole of the work scan's model lane, and its authority
ends where :class:`~station_api.workscan.reading.RoomReading` ends: a list of
``(seq, signal)`` pairs and a list of refusals. It records nothing, opens no
task, approves nothing and returns no text.

Four gates, in this order
--------------------------
1. **the ceiling.** Before a request is built,
   :meth:`~station_api.agent.model_calls.ScanModelCallCounter.verdict` asks
   the planning lane's own pure :func:`station_api.agent.budget.check` whether
   one more turn may be spent. A refusal here costs nothing because nothing
   was sent, and every line in the batch is reported with the reason.
2. **the batch.** A turn carries at most
   :data:`~station_api.workreader.protocol.MAX_LINES_PER_TURN` lines, so a
   room with many lines becomes more turns rather than a larger request - and
   how many turns there may be is gate 1's answer, not the room's.
3. **the registry.** Every ``function.name`` is looked up in
   :data:`~station_api.workreader.protocol.READING_TOOLS` and every argument
   is bound against its declared shape. One unregistered name drops the turn.
4. **the caller.** What comes back is an *input* to candidate production, not
   a candidate. :func:`station_api.workscan.candidates.derive_from_room`
   re-applies the prohibition registry before it consults a verdict, so a
   verdict about a line this product refuses to propose work from produces a
   refusal and never a candidate.

Nothing here is stored and nothing here is shown
-------------------------------------------------
``PlanProposal.text`` - what the model said in words - is **never read** on
this path. There is no field for it on :class:`RoomReading` and no sentence
this module writes quotes it. ADR-0012 1's rule about the reasoning field is
unchanged and this lane never touches that field either; the only thing taken
off a proposal here is ``calls``, ``failure`` and ``finish_reason``.

The provider is told the minimum
---------------------------------
A :class:`~station_api.workscan.reading.ReadableLine` carries a sequence
number and text. It carries no room name, no author, no timestamp, no task and
nothing from the vault - so this module has nothing of that kind to send even
if sending it were wanted, which is the only form of that promise worth
making (ADR-0014 5).
"""

from __future__ import annotations

from collections.abc import Sequence

from station_api.agent.model_calls import ScanModelCallCounter
from station_api.opencode.errors import OpenCodeError
from station_api.opencode.planner import FINISH_TOOL_CALLS
from station_api.opencode.service import OpenCodeService
from station_api.workreader.errors import ReadingProtocolError
from station_api.workreader.protocol import (
    MAX_LINES_PER_TURN,
    READING_MAX_OUTPUT_TOKENS,
    build_messages,
    functions,
    read_calls,
)
from station_api.workscan.reading import (
    LineVerdict,
    ReadableLine,
    ReadingRefusal,
    ReadingRefusalReason,
    RoomReading,
)

#: Longest sentence this module writes about a refusal. The provider's own
#: failure text is quoted into it, and a truncated provider error is the one
#: message a person needs whole - ``planner/service.py``'s number, for the
#: same reason.
MAX_DETAIL_CHARS = 4_000

#: What is said about every line in a batch the ceiling stopped.
CEILING_DETAIL = (
    "Bu satir bir modele okutulmadi: bu tarama icin ayrilan model cagrisi "
    "tavani doldu ({used}/{ceiling}). Satir okundu ve gosteriliyor; aday "
    "uretilmedi. Daha az oda secip taramayi tekrar calistirabilirsiniz."
)

#: What is said when the provider refused, failed or never answered.
FAILED_DETAIL = (
    "Bu satir icin model cevabi alinamadi. Satir okundu ve gosteriliyor; aday "
    "uretilmedi. Saglayicinin bildirdigi: {reason}"
)

#: What is said when an answer came back and this build would not use it.
REFUSED_DETAIL = (
    "Model bu satirin bulundugu tur icin kullanilamayacak bir cevap dondurdu "
    "ve tur butunuyle reddedildi. Satir okundu ve gosteriliyor; aday "
    "uretilmedi. Gerekce: {reason}"
)

#: What is said when the answer was cut off at the output ceiling.
#:
#: Its own sentence rather than :data:`FAILED_DETAIL` with a different word
#: in it, because it is a different fact: nothing was refused, the answer
#: simply did not finish. ``planner/service.py`` draws the same line and for
#: the same reason - a cut is not a decision.
TRUNCATED_REASON = (
    "yanit cikti tavanina dayanip kesildi (sonlanma nedeni: length); "
    "siniflandirma tamamlanmadi"
)


class WorkReaderService:
    """Reads batches of room lines with the selected model, when asked to.

    It owns no connection: :class:`~station_api.opencode.service.OpenCodeService`
    holds the credential, the redaction window, the host allow-list and the
    one-attempt rule, and this class asks it for a turn. That is why
    ``OUTBOUND_CLIENT_MODULES`` stays at five (ADR-0014 8).

    There is no timer, no thread and no background task here, and no
    conversation is kept between turns: a turn happens inside the request that
    asked for it and is complete when it returns.
    """

    def __init__(self, *, opencode: OpenCodeService) -> None:
        self._opencode = opencode

    def classify(
        self, lines: Sequence[ReadableLine], *, counter: ScanModelCallCounter
    ) -> RoomReading:
        """Classify these lines, spending at most what the ceiling allows.

        ``counter`` is the **scan's**, not this room's, and it is deliberately
        passed in rather than created here: the ceiling bounds one user action,
        and a counter created per room would turn a ten-room scan into ten
        ceilings.
        """
        verdicts: list[LineVerdict] = []
        refusals: list[ReadingRefusal] = []
        spent = 0

        for start in range(0, len(lines), MAX_LINES_PER_TURN):
            batch = tuple(lines[start : start + MAX_LINES_PER_TURN])
            if not batch:  # pragma: no cover - range() cannot produce one
                continue

            allowed = counter.verdict()
            if not allowed.allowed:
                refusals.extend(
                    _refuse(
                        batch,
                        ReadingRefusalReason.READING_CEILING,
                        CEILING_DETAIL.format(
                            used=counter.used, ceiling=counter.max_model_calls
                        ),
                    )
                )
                continue

            try:
                proposal = self._opencode.propose_plan(
                    messages=build_messages(batch),
                    functions=functions(),
                    # Stated by the lane that spends it rather than inherited:
                    # this lane's answer is a few integers, so its truncation
                    # guard is its own number and not the planning lane's.
                    max_output_tokens=READING_MAX_OUTPUT_TOKENS,
                )
            except (OpenCodeError, ReadingProtocolError) as exc:
                # Nothing left the process, or the connection refused before
                # anything was billed. Not counted: a turn is counted when an
                # answer came back and was parsed, which is the planning
                # lane's rule and the only one that means the same thing on
                # both lanes.
                refusals.extend(
                    _refuse(
                        batch,
                        ReadingRefusalReason.MODEL_FAILED,
                        FAILED_DETAIL.format(reason=str(exc)),
                    )
                )
                continue

            spent = counter.record_call()

            if proposal.failure is not None:
                refusals.extend(
                    _refuse(
                        batch,
                        ReadingRefusalReason.MODEL_FAILED,
                        FAILED_DETAIL.format(reason=proposal.failure.detail),
                    )
                )
                continue

            if not proposal.calls:
                # Two different silences, and only one of them is an answer.
                # ``stop`` with no call is the model saying "no work in this
                # batch", which is a valid answer and produces nothing.
                # Anything else - a cut, a filter, a reason we do not read -
                # is a turn that did not finish, and reporting it as "no work"
                # would turn a failure into a finding.
                if proposal.finish_reason == FINISH_TOOL_CALLS:
                    refusals.extend(
                        _refuse(
                            batch,
                            ReadingRefusalReason.MODEL_REFUSED,
                            REFUSED_DETAIL.format(
                                reason=(
                                    "saglayici 'tool_calls' bildirdi fakat "
                                    "hicbir cagri gondermedi"
                                )
                            ),
                        )
                    )
                elif proposal.finish_reason != "stop":
                    refusals.extend(
                        _refuse(
                            batch,
                            ReadingRefusalReason.MODEL_FAILED,
                            FAILED_DETAIL.format(
                                reason=(
                                    TRUNCATED_REASON
                                    if proposal.finish_reason == "length"
                                    else (
                                        "tanimadigimiz bir sonlanma nedeni: "
                                        f"'{proposal.finish_reason}'"
                                    )
                                )
                            ),
                        )
                    )
                continue

            try:
                resolved = read_calls(proposal.calls, count=len(batch))
            except (ReadingProtocolError, OpenCodeError) as exc:
                refusals.extend(
                    _refuse(
                        batch,
                        ReadingRefusalReason.MODEL_REFUSED,
                        REFUSED_DETAIL.format(reason=str(exc)),
                    )
                )
                continue

            verdicts.extend(
                LineVerdict(seq=batch[index - 1].seq, signal=signal)
                for index, signal in resolved
            )

        return RoomReading(
            verdicts=tuple(verdicts),
            refusals=tuple(refusals),
            model_calls_used=spent,
        )


def _refuse(
    batch: Sequence[ReadableLine], reason: ReadingRefusalReason, detail: str
) -> list[ReadingRefusal]:
    """One refusal per line, never one for the batch.

    A person reads a list of lines; a refusal attached to "the batch" would be
    a refusal attached to a boundary this build chose and nobody else can see.
    """
    bounded = detail[:MAX_DETAIL_CHARS]
    return [
        ReadingRefusal(seq=line.seq, reason=reason, detail=bounded) for line in batch
    ]


__all__ = [
    "CEILING_DETAIL",
    "FAILED_DETAIL",
    "MAX_DETAIL_CHARS",
    "REFUSED_DETAIL",
    "TRUNCATED_REASON",
    "WorkReaderService",
]
