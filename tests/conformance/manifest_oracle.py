"""The pinned official *document generator*, made runnable as a test oracle.

Stage 3 hand-wrote the shape of ``/openapi.json`` and
``/.well-known/agent.json`` from a reading of the live service, and got the
signed lane wrong: it put the ``sig``/``nonce`` constraints directly under
``schema.properties``, where the reference does not publish them. A fixture
written from a reading can only ever prove that the reading and the code
agree with each other.

So the reference documents are no longer written. They are **generated**, by
executing the pinned ``src/manifest.py`` and asking it for the two documents
the projection reads. Whatever shape the official generator emits is the
shape the tests assert against, and a hand edit to the stored copy is caught
by :mod:`tests.conformance.test_manifest_oracle`.

Why the two shims
-----------------
``manifest.py`` imports ``store``, which imports ``orjson`` and POSIX-only
``fcntl`` at module level. Both are used **only inside the store's runtime
persistence functions** - ``flock`` around the counter file, ``orjson`` for
the record log - and document generation calls none of them. Two minimal
modules satisfy the imports so the real generator can run on Windows; no
shimmed behaviour is exercised while a document is produced. The bytes that
run are the pinned bytes.

``didkey`` additionally imports PyNaCl, which this project already carries as
a test-only dependency for the AC-05 independent verifier. It is not shimmed.
"""

from __future__ import annotations

import json
import sys
import tomllib
import types
from pathlib import Path
from typing import Any

from tests.conformance.oracle import verify_vendor_hashes

#: The commit every generated document belongs to. Same pin as the sweep and
#: signer oracles; adding files to the vendor directory did not move it.
PINNED_COMMIT = "7707cb63ebf638e8ef0cf59d1364818b9fef7d24"

#: The origin the pinned ``app.py`` would build from a request Host header,
#: and the one Station's own source registry is fixed to.
BASE_URL = "https://technocore.chat"

#: ``app.py`` at this commit: ``MAX_BODY = 256 << 10``.
MAX_BODY_BYTES = 256 << 10

#: Imported under their upstream names because the pinned modules import each
#: other that way. Saved and restored around generation so a test session is
#: left exactly as it was found.
_MODULE_NAMES = ("config", "didkey", "store", "manifest")


def _install_shims() -> None:
    """Satisfy two imports whose behaviour document generation never uses."""
    if "fcntl" not in sys.modules:
        fcntl = types.ModuleType("fcntl")
        fcntl.LOCK_EX = 2  # type: ignore[attr-defined]
        fcntl.LOCK_UN = 8  # type: ignore[attr-defined]
        fcntl.flock = lambda *args, **kwargs: None  # type: ignore[attr-defined]
        sys.modules["fcntl"] = fcntl

    if "orjson" not in sys.modules:
        orjson = types.ModuleType("orjson")
        orjson.dumps = lambda obj, *a, **k: json.dumps(obj).encode()  # type: ignore[attr-defined]
        orjson.loads = lambda raw, *a, **k: json.loads(raw)  # type: ignore[attr-defined]
        orjson.JSONDecodeError = ValueError  # type: ignore[attr-defined]
        sys.modules["orjson"] = orjson


def pinned_version(vendor_root: Path) -> str:
    """``project.version`` of the pinned ``pyproject.toml``.

    Read rather than typed in: ``app.py`` derives ``VERSION`` the same way, so
    the version carried by the generated documents is the pinned commit's own
    and no hand-entered value sits in the chain.
    """
    data = tomllib.loads((vendor_root / "pyproject.toml").read_text(encoding="utf-8"))
    version = data["project"]["version"]
    if not isinstance(version, str):  # pragma: no cover - malformed pin
        raise AssertionError("pinned pyproject.toml has no string project.version")
    return version


def generate_documents(vendor_root: Path) -> dict[str, Any]:
    """Run the pinned generator and return what it produces.

    Returns ``{"openapi": ..., "agent": ..., "version": ...}``. Refuses to run
    against a modified reference, exactly like the sweep and signer oracles.
    """
    verify_vendor_hashes(vendor_root)
    _install_shims()

    source_root = vendor_root / "src"
    saved = {name: sys.modules.pop(name, None) for name in _MODULE_NAMES}
    sys.path.insert(0, str(source_root))
    try:
        # Deliberately late and isolated: these are the pinned modules,
        # imported under their upstream names and removed again below.
        import config
        import manifest

        version = pinned_version(vendor_root)
        openapi = manifest.openapi_document(
            BASE_URL, version, MAX_BODY_BYTES, config.MAX_WAIT
        )
        agent = manifest.agent_manifest(
            BASE_URL,
            version,
            config.RATE_READ,
            config.RATE_WRITE,
            config.RATE_ROOMS_PER_DAY,
            config.MAX_WAIT,
        )
    finally:
        sys.path.remove(str(source_root))
        for name in _MODULE_NAMES:
            sys.modules.pop(name, None)
            if saved[name] is not None:
                sys.modules[name] = saved[name]

    return {"openapi": openapi, "agent": agent, "version": version}


def serialise(document: Any) -> bytes:
    """The exact bytes a stored reference document holds.

    ``sort_keys=False`` on purpose: the generator's own key order is part of
    what is being recorded, and re-sorting would hide a reordering upstream.
    """
    text = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False)
    return (text + "\n").encode("utf-8")


__all__ = [
    "BASE_URL",
    "MAX_BODY_BYTES",
    "PINNED_COMMIT",
    "generate_documents",
    "pinned_version",
    "serialise",
]
