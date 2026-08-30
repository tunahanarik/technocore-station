"""The pinned official reference, made runnable as a test oracle.

Two oracles live here, and neither is a second-hand copy of the reference's
behaviour. That distinction is the whole point: a hand-written "expected
sweep" would only ever prove that two of my own implementations agree.

**The sweep oracle** runs the pinned ``clean_text`` itself. ``src/store.py``
cannot simply be imported - it pulls in ``orjson``, ``config``, ``didkey`` and
Linux-only ``fcntl``, none of which belong anywhere near this project's
runtime. So the module is parsed with ``ast``, the normative nodes are
isolated by name, and *those nodes* are compiled and executed in a throwaway
namespace. The bytes that run are the pinned bytes.

**The signer oracle** invokes ``scripts/sign.py`` as a subprocess, which is
how a human would use it. Its output is compared character for character.

Neither oracle writes to the vendor directory, and the recorded SHA-256 of
every vendor file is checked before either is used.

Scope note: the signer oracle passes text through ``argv``, so it is used only
with well-formed Unicode. Lone surrogates are covered by the sweep oracle,
which runs in-process and needs no encoding round-trip.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path

#: The commit every vendored file must belong to.
PINNED_COMMIT = "7707cb63ebf638e8ef0cf59d1364818b9fef7d24"


class OracleStoreError(Exception):
    """Stands in for the reference's ``StoreError``.

    ``clean_text`` raises ``StoreError`` for empty and over-length text. The
    real class carries HTTP status plumbing we neither have nor need; only
    the *fact* of the refusal is normative.
    """


def verify_vendor_hashes(vendor_root: Path) -> None:
    """Refuse to run either oracle against a modified reference."""
    checksums = (vendor_root / "SHA256SUMS").read_text(encoding="utf-8").strip().splitlines()
    if not checksums:
        raise AssertionError("SHA256SUMS is empty")

    for line in checksums:
        expected, relative = line.split(maxsplit=1)
        actual = hashlib.sha256((vendor_root / relative.strip()).read_bytes()).hexdigest()
        if actual != expected:
            raise AssertionError(f"vendor file modified, oracle is not trustworthy: {relative}")


def _module_from_nodes(nodes: list[ast.stmt], filename: str) -> dict[str, object]:
    """Compile and execute a hand-picked list of top-level nodes."""
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, object] = {
        "unicodedata": unicodedata,
        "StoreError": OracleStoreError,
    }
    # Executing the pinned reference's own AST nodes is the point of this
    # helper: it is what makes the comparison differential rather than a
    # restatement of my own understanding.
    exec(compile(module, filename, "exec"), namespace)  # noqa: S102
    return namespace


def load_official_sweep(vendor_root: Path) -> Callable[[str, int], str]:
    """Return the pinned ``clean_text``, isolated from the rest of the server.

    Raises if the expected nodes are not found, so a reference reorganised
    upstream fails loudly instead of silently testing nothing.
    """
    verify_vendor_hashes(vendor_root)

    path = vendor_root / "src" / "store.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    wanted_constants = {"INVISIBLE_CATEGORIES", "MAX_TEXT_CHARS", "MAX_VALUE_CHARS"}
    found_constants: set[str] = set()
    kept: list[ast.stmt] = []

    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {
                target.id for target in node.targets if isinstance(target, ast.Name)
            } & wanted_constants
            if names:
                found_constants |= names
                kept.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "clean_text":
            kept.append(node)

    if found_constants != wanted_constants:
        raise AssertionError(
            f"reference constants not found in store.py: {wanted_constants - found_constants}"
        )
    if not any(isinstance(node, ast.FunctionDef) for node in kept):
        raise AssertionError("clean_text not found in the pinned store.py")

    namespace = _module_from_nodes(kept, str(path))
    clean_text = namespace["clean_text"]
    if not callable(clean_text):  # pragma: no cover - defensive
        raise AssertionError("clean_text did not compile to a callable")
    return clean_text  # type: ignore[return-value]


def official_limits(vendor_root: Path) -> tuple[int, int]:
    """The reference's ``(MAX_TEXT_CHARS, MAX_VALUE_CHARS)``, read from source."""
    verify_vendor_hashes(vendor_root)
    path = vendor_root / "src" / "store.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    limits: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id in {"MAX_TEXT_CHARS", "MAX_VALUE_CHARS"}
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, int)
            ):
                limits[target.id] = node.value.value

    return limits["MAX_TEXT_CHARS"], limits["MAX_VALUE_CHARS"]


def official_name_pattern(vendor_root: Path) -> str:
    """The reference's ``NAME_RE`` pattern, read from the pinned source."""
    verify_vendor_hashes(vendor_root)
    path = vendor_root / "src" / "store.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "NAME_RE":
                call = node.value
                if isinstance(call, ast.Call) and call.args:
                    first = call.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        return first.value
    raise AssertionError("NAME_RE not found in the pinned store.py")


def official_nonce_pattern(vendor_root: Path) -> str:
    """The nonce pattern the reference signer enforces, read from its source.

    It lives inside ``main()`` as a literal in a ``re.fullmatch`` call rather
    than as a module constant, so it is located structurally: the string
    argument of a ``fullmatch`` call whose value is a digit class.
    """
    verify_vendor_hashes(vendor_root)
    path = vendor_root / "scripts" / "sign.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        function = node.func
        if not (isinstance(function, ast.Attribute) and function.attr == "fullmatch"):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            if "0-9" in first.value:
                return first.value
    raise AssertionError("nonce pattern not found in the pinned sign.py")


def _run_signer(vendor_root: Path, arguments: list[str]) -> list[str]:
    """Invoke the pinned signer and return its stdout lines."""
    verify_vendor_hashes(vendor_root)
    script = vendor_root / "scripts" / "sign.py"
    result = subprocess.run(  # noqa: S603 - fixed interpreter, pinned script
        [sys.executable, str(script), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"reference signer failed: {result.stderr[:400]}")
    return result.stdout.strip().splitlines()


def official_did(vendor_root: Path, seed_hex: str) -> str:
    """The reference's ``did:key`` for a TEST-ONLY 64-hex seed."""
    return _run_signer(vendor_root, ["did", "--seed", seed_hex])[0]


def official_message_signature(
    vendor_root: Path, *, seed_hex: str, room: str, nonce: str, text: str
) -> tuple[str, str]:
    """The reference's ``(did, signature)`` for a room message."""
    lines = _run_signer(vendor_root, ["say", "--seed", seed_hex, room, nonce, text])
    return lines[0], lines[1]


def official_note_signature(
    vendor_root: Path, *, seed_hex: str, namespace: str, key: str, nonce: str, value: str
) -> tuple[str, str]:
    """The reference's ``(did, signature)`` for a note."""
    lines = _run_signer(
        vendor_root, ["set", "--seed", seed_hex, namespace, key, nonce, value]
    )
    return lines[0], lines[1]


__all__ = [
    "PINNED_COMMIT",
    "OracleStoreError",
    "load_official_sweep",
    "official_did",
    "official_limits",
    "official_message_signature",
    "official_name_pattern",
    "official_nonce_pattern",
    "official_note_signature",
    "verify_vendor_hashes",
]
