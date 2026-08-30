"""``technocore-conform`` - inspect the write contract from a terminal.

The tool exists so a human can answer "what exactly would be stored, and does
this signature cover it?" without running Station, and without trusting
Station's answer.

Deliberately absent
-------------------
**There is no sign command.** Signing needs a seed, and a seed must never be a
command-line argument: argv is visible to other processes, lands in shell
history, and appears in crash dumps. Real signing happens inside Station,
where the seed is unwrapped from the DPAPI vault for the duration of one
operation - that is Stage 4. So this CLI reads, canonicalises and *verifies*,
which needs only public material.

For the same reason there is no passphrase argument, no seed file option and
no environment-variable seed. The pinned reference's ``--seed`` flag is a
convenience for a demo; it is not a pattern to copy.

The tool makes no network request and writes no telemetry. It reads stdin and
the arguments you pass, and writes to stdout.

Input convention
----------------
Text and note values come from **stdin**, never from argv, so shell quoting
cannot change what gets signed. One trailing line terminator is stripped,
because ``echo`` adds one and it is not part of the value. That cannot alter
wire semantics in the default mode - a newline sweeps to a space and then
trims away - but it does matter under ``--stored``, where the input is
asserted to be exactly what the server holds.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from technocore_conform._version import __version__
from technocore_conform.canonical import (
    CanonicalPayload,
    canonical_message,
    canonical_message_from_swept,
    canonical_note,
    canonical_note_from_swept,
)
from technocore_conform.errors import ConformanceError
from technocore_conform.selftest import run_self_test
from technocore_conform.signature import verify_payload
from technocore_conform.sweep import sweep_message, sweep_note_value

#: The value passed, and the contract verified.
EXIT_OK = 0

#: A conformance failure: text refused, signature malformed, verification
#: failed, or the self-test did not pass. Distinct from a usage error so a
#: script can tell "you asked wrongly" from "the answer is no".
EXIT_FAILURE = 1

#: argparse's own exit code for a malformed command line.
EXIT_USAGE = 2

#: Bumped whenever the --json shape changes incompatibly.
OUTPUT_VERSION = 1

_TOOL = "technocore-conform"


def _read_stdin() -> str:
    """Read the value, dropping one shell line terminator."""
    data = sys.stdin.read()
    if data.endswith("\r\n"):
        return data[:-2]
    if data.endswith("\n"):
        return data[:-1]
    return data


def _emit(payload: dict[str, Any], *, as_json: bool, lines: Sequence[str]) -> None:
    """Write the result: strict JSON, or plain lines."""
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    for line in lines:
        print(line)


def _fail(message: str, *, as_json: bool, command: str) -> int:
    """Report a conformance failure on the right stream."""
    if as_json:
        print(
            json.dumps(
                {
                    "tool": _TOOL,
                    "output_version": OUTPUT_VERSION,
                    "command": command,
                    "ok": False,
                    "error": message,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        print(message, file=sys.stderr)
    return EXIT_FAILURE


def _cmd_sweep(args: argparse.Namespace) -> int:
    command = f"sweep.{args.kind}"
    text = _read_stdin()
    try:
        swept = sweep_message(text) if args.kind == "message" else sweep_note_value(text)
    except ConformanceError as exc:
        return _fail(str(exc), as_json=args.json, command=command)

    _emit(
        {
            "tool": _TOOL,
            "output_version": OUTPUT_VERSION,
            "command": command,
            "ok": True,
            "swept": swept,
            "changed": swept != text,
            "chars": len(swept),
        },
        as_json=args.json,
        lines=[swept],
    )
    return EXIT_OK


def _build_payload(args: argparse.Namespace, text: str) -> CanonicalPayload:
    """Construct the payload named by the sub-command."""
    if args.kind == "message":
        if args.stored:
            return canonical_message_from_swept(
                room=args.room, nonce=args.nonce, swept_text=text
            )
        return canonical_message(room=args.room, nonce=args.nonce, text=text)
    if args.stored:
        return canonical_note_from_swept(
            namespace=args.namespace, key=args.key, nonce=args.nonce, swept_value=text
        )
    return canonical_note(
        namespace=args.namespace, key=args.key, nonce=args.nonce, value=text
    )


def _cmd_canonical(args: argparse.Namespace) -> int:
    command = f"canonical.{args.kind}"
    try:
        payload = _build_payload(args, _read_stdin())
    except (ConformanceError, ValueError) as exc:
        return _fail(str(exc), as_json=args.json, command=command)

    _emit(
        {
            "tool": _TOOL,
            "output_version": OUTPUT_VERSION,
            "command": command,
            "ok": True,
            "canonical": payload.canonical,
            "swept": payload.swept_text,
            "changed_by_sweep": payload.changed_by_sweep,
            "structural_separators": payload.structural_separators,
            "bytes": len(payload.canonical_bytes),
        },
        as_json=args.json,
        lines=[payload.canonical],
    )
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace) -> int:
    command = f"verify.{args.kind}"
    try:
        payload = _build_payload(args, _read_stdin())
        verify_payload(payload, did=args.did, signature=args.signature)
    except (ConformanceError, ValueError) as exc:
        return _fail(f"{type(exc).__name__}: {exc}", as_json=args.json, command=command)

    _emit(
        {
            "tool": _TOOL,
            "output_version": OUTPUT_VERSION,
            "command": command,
            "ok": True,
            "did": args.did,
            "canonical": payload.canonical,
        },
        as_json=args.json,
        lines=["ok"],
    )
    return EXIT_OK


def _cmd_self_test(args: argparse.Namespace) -> int:
    result = run_self_test()
    payload = {
        "tool": _TOOL,
        "output_version": OUTPUT_VERSION,
        "command": "self-test",
        "ok": result.passed,
        "bundle_digest": result.bundle_digest,
        "bundle_vectors": result.bundle_vectors,
        "upstream_commit": result.upstream_commit,
        "package_version": result.package_version,
        "python_version": result.python_version,
        "unicode_version": result.unicode_version,
        "bundle_unicode_version": result.bundle_unicode_version,
        "checks": [
            {"name": check.name, "passed": check.passed, "vectors": check.vectors}
            for check in result.checks
        ],
        "failures": list(result.failures),
    }

    lines = [f"self-test: {'PASS' if result.passed else 'FAIL'}"]
    lines += [
        f"  {check.name:<18} {'ok' if check.passed else 'FAILED':<7} {check.detail}"
        for check in result.checks
    ]
    lines += [
        f"  bundle   {result.bundle_digest[:16]} ({result.bundle_vectors} vectors)",
        f"  upstream {result.upstream_commit[:12]}",
        f"  runtime  technocore-conform {result.package_version}, "
        f"Python {result.python_version}, Unicode {result.unicode_version}",
    ]

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        stream = sys.stdout if result.passed else sys.stderr
        for line in lines:
            print(line, file=stream)

    return EXIT_OK if result.passed else EXIT_FAILURE


def _cmd_version(args: argparse.Namespace) -> int:
    _emit(
        {
            "tool": _TOOL,
            "output_version": OUTPUT_VERSION,
            "command": "version",
            "ok": True,
            "version": __version__,
        },
        as_json=args.json,
        lines=[__version__],
    )
    return EXIT_OK


def _add_message_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--room", required=True, help="room name")
    parser.add_argument("--nonce", required=True, help="1-19 ASCII digits")


def _add_note_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--namespace", required=True, help="note namespace")
    parser.add_argument("--key", required=True, help="note key")
    parser.add_argument("--nonce", required=True, help="1-19 ASCII digits")


def _add_stored_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stored",
        action="store_true",
        help=(
            "treat stdin as the text the server already stores; refuse it if it is "
            "not already in swept form, instead of sweeping it"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """The full command line. No seed and no passphrase option exists."""
    parser = argparse.ArgumentParser(
        prog=_TOOL,
        description=(
            "Inspect the Technocore write contract: sweep, canonicalise and verify. "
            "Reads text from stdin. Never signs, and never accepts a seed."
        ),
    )
    parser.add_argument(
        "--json", action="store_true", help="emit strict, versioned JSON on stdout"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sweep_parser = sub.add_parser("sweep", help="show the text as it would be stored")
    sweep_kinds = sweep_parser.add_subparsers(dest="kind", required=True)
    sweep_kinds.add_parser("message", help="4096-character limit")
    sweep_kinds.add_parser("note", help="8192-character limit")
    sweep_parser.set_defaults(handler=_cmd_sweep)

    canonical_parser = sub.add_parser("canonical", help="print the string that is signed")
    canonical_kinds = canonical_parser.add_subparsers(dest="kind", required=True)
    canonical_message_parser = canonical_kinds.add_parser("message")
    _add_message_fields(canonical_message_parser)
    _add_stored_flag(canonical_message_parser)
    canonical_note_parser = canonical_kinds.add_parser("note")
    _add_note_fields(canonical_note_parser)
    _add_stored_flag(canonical_note_parser)
    canonical_parser.set_defaults(handler=_cmd_canonical)

    verify_parser = sub.add_parser("verify", help="check a signature over a payload")
    verify_kinds = verify_parser.add_subparsers(dest="kind", required=True)
    verify_message_parser = verify_kinds.add_parser("message")
    _add_message_fields(verify_message_parser)
    verify_note_parser = verify_kinds.add_parser("note")
    _add_note_fields(verify_note_parser)
    for signed in (verify_message_parser, verify_note_parser):
        # DID and signature are public material, so argv is fine for them.
        signed.add_argument("--did", required=True, help="did:key of the signer")
        signed.add_argument("--signature", required=True, help="86-char base64url")
        _add_stored_flag(signed)
    verify_parser.set_defaults(handler=_cmd_verify)

    self_test_parser = sub.add_parser(
        "self-test", help="replay the shipped conformance vectors"
    )
    self_test_parser.set_defaults(handler=_cmd_self_test)

    version_parser = sub.add_parser("version", help="print the package version")
    version_parser.set_defaults(handler=_cmd_version)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns an exit code rather than calling ``sys.exit``."""
    parser = build_parser()
    args = parser.parse_args(argv)
    # Only some sub-commands define --stored; normalise so handlers can read it.
    if not hasattr(args, "stored"):
        args.stored = False
    handler: object = args.handler
    assert callable(handler)
    result = handler(args)
    assert isinstance(result, int)
    return result


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    raise SystemExit(main())


__all__ = [
    "EXIT_FAILURE",
    "EXIT_OK",
    "EXIT_USAGE",
    "OUTPUT_VERSION",
    "build_parser",
    "main",
]
