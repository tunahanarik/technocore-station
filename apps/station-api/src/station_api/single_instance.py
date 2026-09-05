"""One Station per data directory.

ADR-0010 8. Until this file there was neither a single-instance guard nor a
shutdown handler, so double-clicking the icon put two processes on one SQLite
file and one ``audit/v1/chain-head.json``. Whether that race actually
corrupts anything was **not measured**, and this repository does not write
"it is fine" about something nobody looked at (ADR-0005 2's rule, applied to
a concurrency question): the guard exists because the cost of finding out the
hard way is an audit chain, not because a corruption was reproduced.

The mechanism is the one the credential store already uses -
``os.open`` with ``O_CREAT | O_EXCL`` - for the reason ADR-0010 8 gives: it
needs no ``ctypes``, no third-party package and no Windows-only call, and the
kernel does the mutual exclusion. What it deliberately is **not**:

* **Not an IPC channel.** A second launch does not hand the first one a
  "open a new tab" message. That is a second local listener or a named pipe,
  and the product's contract is one loopback listener with an origin check in
  front of it.
* **Not a liveness probe.** ``os.kill(pid, 0)`` is the usual trick and on
  Windows CPython implements ``os.kill`` as ``OpenProcess`` +
  ``TerminateProcess``, so signal ``0`` would *terminate* the process it was
  asked about. A stale lock is therefore reported with the path to delete
  rather than cleaned up on a guess.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final

#: Name of the lock file inside the data directory. Deliberately inside the
#: data directory rather than ``%TEMP%``: the thing being protected is that
#: directory's database and audit chain, so the lock belongs beside them and
#: the product still writes nothing to ``%TEMP%`` (ADR-0010 2).
LOCK_FILENAME: Final = "station.lock"

#: ``os.O_BINARY`` exists on Windows only; zero is the no-op elsewhere.
_BINARY_FLAG: int = getattr(os, "O_BINARY", 0)


class AlreadyRunningError(RuntimeError):
    """Another Station holds this data directory.

    Carries the lock path in its message on purpose. A refusal a user cannot
    clear is a refusal that gets worked around by deleting the data
    directory, which is the one action ADR-0010 5 spends a whole section
    keeping people away from.
    """


@dataclass(frozen=True, slots=True)
class InstanceLock:
    """A held lock. Releasing is idempotent and never raises."""

    path: Path

    def release(self) -> None:
        """Remove the lock file. Missing is success, not an error."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            return
        except OSError:  # pragma: no cover - the file is ours and local
            return

    def __enter__(self) -> InstanceLock:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


def acquire(data_dir: Path) -> InstanceLock:
    """Claim this data directory for this process, or refuse.

    The file is created with ``O_EXCL`` so the check and the claim are one
    kernel operation; two processes racing here cannot both win. What lands
    inside is the process id and the moment, which is diagnostic text and not
    a secret - no token, no path outside the data directory, no identity.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / LOCK_FILENAME

    try:
        handle = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | _BINARY_FLAG,
            0o600,
        )
    except FileExistsError as exc:
        raise AlreadyRunningError(
            "Technocore Station bu veri dizini icin zaten calisiyor. "
            "Ikinci bir kopya ayni veritabanini ve ayni denetim zincirini "
            "acmaz. Acik kopya yoksa su dosyayi silip yeniden baslatin: "
            f"{lock_path}"
        ) from exc

    stamp = f"{os.getpid()} {datetime.now(UTC).isoformat()}\n"
    try:
        os.write(handle, stamp.encode("utf-8"))
    finally:
        os.close(handle)

    return InstanceLock(path=lock_path)


__all__ = ["LOCK_FILENAME", "AlreadyRunningError", "InstanceLock", "acquire"]
