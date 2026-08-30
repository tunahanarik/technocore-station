"""The CLI seed-import boundary.

Two properties are under test:

* Only the format the pinned official signer actually uses is accepted, and
  the passphrase-derived form is explicitly refused.
* A raw seed can never arrive over HTTP - there is no such endpoint and no
  such frontend field.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from station_api.seed_import import (
    MAX_SEED_FILE_BYTES,
    SeedImportError,
    parse_official_seed,
)

from tests.conftest import TEST_ONLY_SEED_HEX

pytestmark = pytest.mark.security


def test_bare_hex_seed_is_accepted() -> None:
    assert parse_official_seed(TEST_ONLY_SEED_HEX.encode()) == bytes.fromhex(TEST_ONLY_SEED_HEX)


def test_surrounding_whitespace_is_tolerated() -> None:
    payload = f"\n  {TEST_ONLY_SEED_HEX}  \r\n".encode()
    assert parse_official_seed(payload) == bytes.fromhex(TEST_ONLY_SEED_HEX)


def test_uppercase_hex_is_accepted() -> None:
    assert parse_official_seed(TEST_ONLY_SEED_HEX.upper().encode()) == bytes.fromhex(
        TEST_ONLY_SEED_HEX
    )


def test_keygen_output_shape_is_accepted() -> None:
    """`sign.py keygen` prints exactly these two lines."""
    payload = (
        f"seed: {TEST_ONLY_SEED_HEX}\n"
        "did:  did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp\n"
    ).encode()
    assert parse_official_seed(payload) == bytes.fromhex(TEST_ONLY_SEED_HEX)


def test_passphrase_form_is_refused() -> None:
    """The official script would SHA-256 this. Station must not.

    Deriving a seed from a passphrase replaces 32 bytes of randomness with
    whatever entropy the phrase had, which the project brief forbids.
    """
    with pytest.raises(SeedImportError) as excinfo:
        parse_official_seed(b"correct horse battery staple")
    assert "Paroladan seed turetme" in str(excinfo.value)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"deadbeef",
        b"4c7a1e9b3d5f8027a6c4e91b2d8f0356749ace1b2d4f6081a3c5e7092b4d6f81ff",
        b"gc7a1e9b3d5f8027a6c4e91b2d8f0356749ace1b2d4f6081a3c5e7092b4d6f81",
        b"\xff\xfe\x00binary",
    ],
)
def test_malformed_files_are_refused(payload: bytes) -> None:
    with pytest.raises(SeedImportError):
        parse_official_seed(payload)


def test_multiple_seed_lines_are_refused() -> None:
    payload = f"seed: {TEST_ONLY_SEED_HEX}\nseed: {'11' * 32}\n".encode()
    with pytest.raises(SeedImportError):
        parse_official_seed(payload)


def test_oversized_file_is_refused() -> None:
    with pytest.raises(SeedImportError):
        parse_official_seed(b"a" * (MAX_SEED_FILE_BYTES + 1))


def test_no_http_endpoint_accepts_a_raw_seed(app: FastAPI) -> None:
    """The API surface must expose no seed input at all."""
    document = app.openapi()

    for path in document.get("paths", {}):
        assert "seed" not in path.lower(), f"a seed-shaped route exists: {path}"

    body = json.dumps(document).lower()
    for forbidden in ('"seed"', '"private_key"', '"mnemonic"'):
        assert forbidden not in body, f"OpenAPI mentions {forbidden}"


def test_the_cli_never_takes_a_seed_or_passphrase_argument(api_source_root: Path) -> None:
    """Arguments end up in shell history and in ps output."""
    source = (api_source_root / "station_api" / "cli" / "__main__.py").read_text(
        encoding="utf-8"
    )

    assert "getpass" in source, "passphrases must be read with getpass"
    for forbidden in ('"--seed"', "'--seed'", '"--passphrase"', "'--passphrase'"):
        assert forbidden not in source, f"CLI declares {forbidden}"


def test_the_cli_does_not_log_the_path_or_the_seed(api_source_root: Path) -> None:
    source = (api_source_root / "station_api" / "cli" / "__main__.py").read_text(
        encoding="utf-8"
    )
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("print(", "logger.")):
            assert "seed_path" not in stripped, f"CLI prints the seed path: {stripped}"
            assert "seed.hex" not in stripped, f"CLI prints seed bytes: {stripped}"


def test_frontend_has_no_raw_seed_input(web_source_root: Path) -> None:
    """No textbox, paste target or upload control bound to a raw seed."""
    offenders: list[str] = []
    for path in web_source_root.rglob("*.ts*"):
        if path.name.endswith((".test.ts", ".test.tsx")):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            lowered = line.lower()
            is_input = "<input" in lowered or "<textarea" in lowered or "textfield" in lowered
            if is_input and any(
                marker in lowered for marker in ("seed", "mnemonic", "privatekey")
            ):
                offenders.append(f"{path.name}: {line.strip()[:80]}")

    assert offenders == [], f"frontend exposes a seed-shaped input: {offenders}"
