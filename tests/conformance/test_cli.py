"""The ``technocore-conform`` command line.

Driven as a subprocess, because that is how it is used and because the exit
code and stream contract are part of the interface. Text always goes in on
stdin, so shell quoting cannot change the wire semantics.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest
from technocore_conform import canonical_message, did_key_from_seed, sign_payload
from technocore_conform.cli import EXIT_FAILURE, EXIT_OK, EXIT_USAGE, build_parser

pytestmark = pytest.mark.conformance

#: TEST-ONLY seed. A published fixture, never operational key material.
TEST_ONLY_SEED = "0000000000000000000000000000000000000000000000000000000000000001"


def run_cli(
    *arguments: str, stdin: str = "", timeout: int = 180
) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI exactly as a user would."""
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "technocore_conform", *arguments],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def json_output(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(result.stdout)
    return payload


# --- the commands exist ----------------------------------------------------


def test_every_required_command_is_present() -> None:
    """The command set named in the Stage 2B scope, checked structurally."""
    parser = build_parser()
    commands: set[str] = set()
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if choices and action.option_strings == []:
            commands |= set(choices)

    assert {"sweep", "canonical", "verify", "self-test", "version"} <= commands


def test_version_prints_the_package_version() -> None:
    result = run_cli("version")
    assert result.returncode == EXIT_OK
    assert result.stdout.strip()
    assert result.stderr == ""


# --- sweep -----------------------------------------------------------------


def test_sweep_message_prints_the_stored_form() -> None:
    result = run_cli("sweep", "message", stdin="  merhaba\tdunya  ")
    assert result.returncode == EXIT_OK
    assert result.stdout.rstrip("\r\n") == "merhaba dunya"


def test_sweep_note_uses_the_note_limit() -> None:
    """A 4097-character value is legal as a note and illegal as a message."""
    value = "a" * 4097
    assert run_cli("sweep", "note", stdin=value).returncode == EXIT_OK
    assert run_cli("sweep", "message", stdin=value).returncode == EXIT_FAILURE


def test_sweep_refuses_text_with_nothing_visible() -> None:
    result = run_cli("sweep", "message", stdin="​​")
    assert result.returncode == EXIT_FAILURE
    assert result.stdout == ""
    assert "sweep" in result.stderr


def test_a_trailing_newline_does_not_change_the_result() -> None:
    """One shell line terminator is stripped; the value is unchanged."""
    without = run_cli("canonical", "message", "--room", "r", "--nonce", "1", stdin="abc")
    with_newline = run_cli(
        "canonical", "message", "--room", "r", "--nonce", "1", stdin="abc\n"
    )
    assert without.stdout == with_newline.stdout


# --- canonical -------------------------------------------------------------


def test_canonical_message_shape() -> None:
    result = run_cli(
        "canonical", "message", "--room", "lobby", "--nonce", "007", stdin="  merhaba  "
    )
    assert result.returncode == EXIT_OK
    assert result.stdout.rstrip("\r\n") == "lobby|007|merhaba"


def test_canonical_note_shape() -> None:
    result = run_cli(
        "canonical",
        "note",
        "--namespace",
        "profile",
        "--key",
        "bio",
        "--nonce",
        "1",
        stdin="deger",
    )
    assert result.returncode == EXIT_OK
    assert result.stdout.rstrip("\r\n") == "profile|bio|1|deger"


def test_canonical_keeps_pipes_in_the_text() -> None:
    result = run_cli("canonical", "message", "--room", "r", "--nonce", "1", stdin="a|b|c")
    assert result.stdout.rstrip("\r\n") == "r|1|a|b|c"


def test_canonical_refuses_an_invalid_room() -> None:
    result = run_cli("canonical", "message", "--room", "BAD", "--nonce", "1", stdin="x")
    assert result.returncode == EXIT_FAILURE
    assert "room" in result.stderr


def test_canonical_refuses_a_unicode_digit_nonce() -> None:
    result = run_cli("canonical", "message", "--room", "r", "--nonce", "١٢٣", stdin="x")
    assert result.returncode == EXIT_FAILURE


def test_stored_mode_refuses_text_that_is_not_already_swept() -> None:
    """``--stored`` asserts this is what the server holds; it does not fix it."""
    padded = run_cli(
        "canonical", "message", "--room", "r", "--nonce", "1", "--stored", stdin="  x  "
    )
    assert padded.returncode == EXIT_FAILURE

    clean = run_cli(
        "canonical", "message", "--room", "r", "--nonce", "1", "--stored", stdin="x"
    )
    assert clean.returncode == EXIT_OK


# --- verify ----------------------------------------------------------------


def _signed() -> tuple[str, str]:
    seed = bytes.fromhex(TEST_ONLY_SEED)
    payload = canonical_message(room="test-room", nonce="1", text="hello world")
    return did_key_from_seed(seed), sign_payload(payload, seed=seed)


def test_verify_accepts_a_good_signature() -> None:
    did, signature = _signed()
    result = run_cli(
        "verify",
        "message",
        "--room",
        "test-room",
        "--nonce",
        "1",
        "--did",
        did,
        "--signature",
        signature,
        stdin="hello world",
    )
    assert result.returncode == EXIT_OK
    assert result.stdout.rstrip("\r\n") == "ok"


def test_verify_rejects_a_tampered_payload() -> None:
    did, signature = _signed()
    result = run_cli(
        "verify",
        "message",
        "--room",
        "test-room",
        "--nonce",
        "2",
        "--did",
        did,
        "--signature",
        signature,
        stdin="hello world",
    )
    assert result.returncode == EXIT_FAILURE
    assert "SignatureMismatchError" in result.stderr


def test_verify_distinguishes_a_malformed_signature() -> None:
    did, signature = _signed()
    result = run_cli(
        "verify",
        "message",
        "--room",
        "test-room",
        "--nonce",
        "1",
        "--did",
        did,
        "--signature",
        signature + "==",
        stdin="hello world",
    )
    assert result.returncode == EXIT_FAILURE
    assert "MalformedSignatureError" in result.stderr


# --- self-test -------------------------------------------------------------


def test_self_test_passes_and_reports_provenance() -> None:
    result = run_cli("self-test")
    assert result.returncode == EXIT_OK
    assert "PASS" in result.stdout
    assert "7707cb63" in result.stdout


# --- JSON output -----------------------------------------------------------


def test_json_output_is_strict_and_versioned() -> None:
    result = run_cli(
        "--json", "canonical", "message", "--room", "r", "--nonce", "1", stdin="x"
    )
    payload = json_output(result)

    assert payload["tool"] == "technocore-conform"
    assert payload["output_version"] == 1
    assert payload["command"] == "canonical.message"
    assert payload["ok"] is True
    assert payload["canonical"] == "r|1|x"


def test_json_failure_is_still_json_and_still_non_zero() -> None:
    result = run_cli("--json", "sweep", "message", stdin="​")
    payload = json_output(result)

    assert result.returncode == EXIT_FAILURE
    assert payload["ok"] is False
    assert payload["error"]


def test_json_self_test_carries_the_runtime_metadata() -> None:
    payload = json_output(run_cli("--json", "self-test"))

    assert payload["ok"] is True
    assert payload["upstream_commit"] == "7707cb63ebf638e8ef0cf59d1364818b9fef7d24"
    assert payload["bundle_digest"]
    assert payload["python_version"]
    assert payload["unicode_version"]
    assert len(payload["checks"]) == 8


def test_json_output_never_carries_key_material() -> None:
    """The CLI accepts no seed, so it can emit none - checked anyway."""
    for arguments, stdin in (
        (["--json", "self-test"], ""),
        (["--json", "sweep", "message"], "merhaba"),
        (["--json", "canonical", "message", "--room", "r", "--nonce", "1"], "x"),
    ):
        text = run_cli(*arguments, stdin=stdin).stdout.lower()
        for forbidden in ("seed", "private", "passphrase", "mnemonic", "secret"):
            assert forbidden not in text, f"{forbidden} appeared in {arguments}"


# --- what the CLI must never offer -----------------------------------------


def test_there_is_no_sign_command() -> None:
    """Signing needs a seed; a seed must never be an argument."""
    result = run_cli("sign", "message", "--room", "r", "--nonce", "1", stdin="x")
    assert result.returncode == EXIT_USAGE


@pytest.mark.parametrize(
    "flag",
    ["--seed", "--passphrase", "--password", "--key", "--private-key", "--seed-file"],
)
def test_no_secret_carrying_flag_exists(flag: str) -> None:
    """argv is visible to other processes and lands in shell history."""
    result = run_cli(
        "canonical", "message", "--room", "r", "--nonce", "1", flag, "x", stdin="y"
    )
    assert result.returncode == EXIT_USAGE


def test_no_secret_option_is_declared_anywhere_in_the_parser() -> None:
    """Structural check across every sub-parser, not just the ones above."""
    seen: list[str] = []

    def walk(parser: Any) -> None:
        for action in parser._actions:
            seen.extend(action.option_strings)
            choices = getattr(action, "choices", None) or {}
            for name in choices:
                candidate = choices[name]
                if hasattr(candidate, "_actions"):
                    walk(candidate)

    walk(build_parser())
    joined = " ".join(seen).lower()
    for forbidden in ("seed", "passphrase", "password", "private", "secret", "mnemonic"):
        assert forbidden not in joined, f"the CLI declares a {forbidden} option"


def test_usage_error_is_a_different_exit_code_from_a_conformance_failure() -> None:
    """A script must be able to tell asked-wrongly from the-answer-is-no."""
    assert run_cli("no-such-command").returncode == EXIT_USAGE
    assert run_cli("sweep", "message", stdin="​").returncode == EXIT_FAILURE
    assert EXIT_USAGE != EXIT_FAILURE != EXIT_OK
