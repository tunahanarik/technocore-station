"""Read-only spending context. No budget opens here.

The repository said two different things before this package: Package F's
``BUDGET_DETAIL`` text pointed at "G and H2", while the execution plan said G
spends nothing. ADR-0005 9 settled it - :data:`BUDGET_AVAILABLE` stays
``False`` - and this module carries what G *may* honestly show instead.

Everything here is a published figure or a plain statement about where a
control lives. Nothing is measured, nothing is projected, and no field on any
response derived from this module is a currency amount Station computed.

The four things this module refuses to say
------------------------------------------
* **"Unlimited."** A subscription with published caps is not unlimited, and
  presenting it that way is how a person discovers a limit by hitting it.
* **"You have spent X."** Token and cost figures come from the provider or
  they are ``unknown``. A local counter counts what this installation sent;
  it cannot see the rest of a shared subscription, and
  :data:`LOCAL_COUNTER_CAVEAT` says so where the number is shown.
* **"Station has stopped 'Use balance'."** That preference lives in the
  provider's console. Station does not change it, cannot read it, and
  therefore does not claim to have blocked it.
* **"You are within budget."** There is no budget here to be within.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from station_api.opencode.registry import PROVIDER_CONSOLE_URL

#: Unchanged from Package F, and unchanged deliberately (ADR-0005 9). A real
#: budget ceiling and a concurrency limit belong to the executor package.
BUDGET_AVAILABLE: Final[Literal[False]] = False


@dataclass(frozen=True, slots=True)
class PublishedLimit:
    """One usage limit exactly as the provider published it."""

    window: str
    amount_usd: int
    note: str


#: The published caps (ADR-0005 1, read 4 September 2026). Amounts are the
#: provider's, not ours; the window names are theirs too.
PUBLISHED_LIMITS: tuple[PublishedLimit, ...] = (
    PublishedLimit(
        window="5 saat",
        amount_usd=12,
        note="Bes saatlik pencerede yayimlanmis ust sinir.",
    ),
    PublishedLimit(
        window="hafta",
        amount_usd=30,
        note="Haftalik yayimlanmis ust sinir.",
    ),
    PublishedLimit(
        window="ay",
        amount_usd=60,
        note="Aylik yayimlanmis ust sinir.",
    ),
)

#: What happens at the cap, in the provider's own terms.
LIMIT_BEHAVIOUR = (
    "Yayimlanmis sinir dolunca saglayici ucretsiz modellere duser veya "
    "tercihe gore Zen bakiyesinden dusurur."
)

#: Where the "Use balance" preference lives, and who controls it.
USE_BALANCE_STATEMENT = (
    "'Use balance' tercihi saglayicinin kendi konsolundadir "
    f"({PROVIDER_CONSOLE_URL}) ve API uzerinden sorgulanamaz. Station bu "
    "ayari degistirmez ve engelledigini iddia etmez."
)

#: The sentence that must accompany any locally counted figure.
LOCAL_COUNTER_CAVEAT = (
    "Yerel sayac yalnizca bu kurulumun gonderdigini sayar. Paylasilan bir "
    "abonelikte gercek kullanimi kanitlamaz."
)

#: The sentence used wherever a cost or token figure is absent.
UNKNOWN_COST_SENTENCE = (
    "Token ve maliyet bilgisi saglayicidan gelmedi; bilinmiyor. Sifir "
    "yazilmaz."
)

#: The one word this module will not accept about the subscription.
FORBIDDEN_SUBSCRIPTION_WORDS = ("sinirsiz", "unlimited")


def assert_no_unlimited_claim(text: str) -> None:
    """Refuse our own sentence if it calls the subscription unlimited.

    The same shape as ``evidence/language.py``'s charter guard: a rule about
    what the product may say is worth enforcing on the product's own strings,
    because those are the ones a future edit will get wrong.
    """
    lowered = text.casefold()
    for word in FORBIDDEN_SUBSCRIPTION_WORDS:
        if word in lowered:
            raise ValueError(
                f"a spending sentence called the subscription {word!r}"
            )


__all__ = [
    "BUDGET_AVAILABLE",
    "FORBIDDEN_SUBSCRIPTION_WORDS",
    "LIMIT_BEHAVIOUR",
    "LOCAL_COUNTER_CAVEAT",
    "PUBLISHED_LIMITS",
    "UNKNOWN_COST_SENTENCE",
    "USE_BALANCE_STATEMENT",
    "PublishedLimit",
    "assert_no_unlimited_claim",
]
