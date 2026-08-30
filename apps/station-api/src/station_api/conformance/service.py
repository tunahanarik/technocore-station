"""Run the conformance self-test, once, and hand the verdict to the gate.

The self-test is deterministic and reads only shipped package data, so a
result is cached for the life of the process: re-running it per request would
burn Ed25519 verifications to reach the same answer.

The runner is injectable. That is what lets a test prove the write gate
actually closes when conformance fails, without editing the shipped vector
bundle - which is pinned by digest precisely so it cannot be edited.

Fail-closed: ``run_self_test`` never raises, but if a future runner did, this
wrapper turns the exception into a failed verdict rather than letting it
propagate into a request handler where a broad ``except`` might swallow it
into an apparent success.
"""

from __future__ import annotations

from collections.abc import Callable

from technocore_conform import SelfTestResult, run_self_test

#: A callable that produces a verdict. Substituted in tests.
SelfTestRunner = Callable[[], SelfTestResult]


def _failed_result(reason: str) -> SelfTestResult:
    """A verdict that cannot be mistaken for a pass."""
    return SelfTestResult(
        passed=False,
        checks=(),
        failures=(reason,),
        bundle_digest="",
        bundle_vectors=0,
        upstream_commit="",
        package_version="",
        python_version="",
        unicode_version="",
        bundle_unicode_version="",
    )


class ConformanceService:
    """Caches one self-test verdict for the process."""

    def __init__(self, runner: SelfTestRunner = run_self_test) -> None:
        self._runner = runner
        self._result: SelfTestResult | None = None

    def result(self) -> SelfTestResult:
        """The cached verdict, computing it on first use."""
        if self._result is None:
            self._result = self.refresh()
        return self._result

    def refresh(self) -> SelfTestResult:
        """Re-run the self-test and replace the cached verdict."""
        try:
            self._result = self._runner()
        except Exception as exc:
            # Broad on purpose: a crash is never a pass. Letting this escape
            # would put the verdict at the mercy of whatever catches it.
            self._result = _failed_result(f"conformance self-test raised: {exc!r}")
        return self._result

    @property
    def passed(self) -> bool:
        """Whether this build reproduces the pinned reference's behaviour."""
        return self.result().passed


_default: ConformanceService | None = None


def default_conformance_service() -> ConformanceService:
    """The process-wide service, so the self-test runs once per process."""
    # A deliberate process-level singleton: the self-test is deterministic,
    # so one verdict per process is the right granularity.
    global _default
    if _default is None:
        _default = ConformanceService()
    return _default


def reset_default_conformance_service() -> None:
    """Drop the cached singleton. For tests only."""
    global _default
    _default = None


__all__ = [
    "ConformanceService",
    "SelfTestRunner",
    "default_conformance_service",
    "reset_default_conformance_service",
]
