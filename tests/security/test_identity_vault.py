"""DPAPI vault and ``.tcrec`` recovery - AC-10 and AC-11.

The vault tests are real: they call Windows DPAPI and the Windows ACL API. On
a non-Windows machine the vault must fail closed rather than fall back, and
that is what is asserted instead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from station_api.recovery import (
    aad_for_header,
    create_recovery,
    file_fingerprint,
    open_recovery,
)
from station_api.strict_json import canonical_json_bytes
from station_api.vault import DpapiVault, ProtectionMode
from station_api.vault.errors import (
    VaultAlreadyExistsError,
    VaultFormatError,
    VaultNotFoundError,
    VaultUnlockError,
    VaultUnsupportedPlatformError,
)
from station_api.vault.passphrase import PRODUCTION_KDF_POLICY, KdfPolicy
from station_api.vault.paths import new_identity_id
from technocore_conform import did_key_from_seed

from tests.conftest import (
    TEST_ONLY_RECOVERY_PASSPHRASE,
    TEST_ONLY_SEED_HEX,
    TEST_ONLY_VAULT_PASSPHRASE,
    TEST_ONLY_WRONG_PASSPHRASE,
)

pytestmark = pytest.mark.security

IS_WINDOWS = sys.platform == "win32"
windows_only = pytest.mark.skipif(
    not IS_WINDOWS,
    reason="DPAPI is a Windows API; the non-Windows path is asserted separately",
)

TEST_ONLY_SEED = bytes.fromhex(TEST_ONLY_SEED_HEX)


@pytest.fixture
def vault(tmp_path: Path) -> DpapiVault:
    return DpapiVault(tmp_path)


# --- platform boundary -----------------------------------------------------


def test_non_windows_fails_closed_and_never_falls_back(vault: DpapiVault) -> None:
    """There is no fake vault. On an unsupported platform we refuse."""
    capability = vault.capability()
    if IS_WINDOWS:
        assert capability.platform_supported is True
        assert capability.dpapi_available is True
        assert capability.aead_available is True
    else:
        assert capability.platform_supported is False
        assert capability.usable is False
        with pytest.raises(VaultUnsupportedPlatformError):
            vault.store(
                identity_id=new_identity_id(),
                seed=TEST_ONLY_SEED,
                protection=ProtectionMode.DPAPI,
                passphrase=None,
            )


def test_no_fake_vault_implementation_exists(api_source_root: Path) -> None:
    """A silent in-memory fallback would store an unprotected seed."""
    offenders: list[str] = []
    for path in (api_source_root / "station_api" / "vault").rglob("*.py"):
        lowered = path.read_text(encoding="utf-8").lower()
        for smell in ("class fakevault", "class memoryvault", "class dummyvault"):
            if smell in lowered:
                offenders.append(f"{path.name}: {smell}")
    assert offenders == [], f"a fake vault implementation exists: {offenders}"


def test_machine_scope_is_never_used(api_source_root: Path) -> None:
    """CRYPTPROTECT_LOCAL_MACHINE would widen the blob to every account."""
    source = (api_source_root / "station_api" / "vault" / "dpapi.py").read_text(
        encoding="utf-8"
    )
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", '"', "_CRYPTPROTECT_LOCAL_MACHINE =")):
            continue  # the constant is documented as intentionally unused
        assert "_CRYPTPROTECT_LOCAL_MACHINE" not in stripped, stripped


# --- round trip ------------------------------------------------------------


@windows_only
@pytest.mark.parametrize(
    ("protection", "passphrase"),
    [
        (ProtectionMode.DPAPI, None),
        (ProtectionMode.DPAPI_PASSPHRASE, TEST_ONLY_VAULT_PASSPHRASE),
    ],
)
def test_vault_round_trip(
    vault: DpapiVault, protection: ProtectionMode, passphrase: str | None
) -> None:
    identity_id = new_identity_id()
    vault.store(
        identity_id=identity_id,
        seed=TEST_ONLY_SEED,
        protection=protection,
        passphrase=passphrase,
    )
    assert vault.load(identity_id=identity_id, passphrase=passphrase) == TEST_ONLY_SEED


@windows_only
def test_vault_file_contains_no_plaintext_seed(vault: DpapiVault) -> None:
    identity_id = new_identity_id()
    path = vault.store(
        identity_id=identity_id,
        seed=TEST_ONLY_SEED,
        protection=ProtectionMode.DPAPI_PASSPHRASE,
        passphrase=TEST_ONLY_VAULT_PASSPHRASE,
    )
    blob = path.read_bytes()

    assert TEST_ONLY_SEED not in blob
    assert TEST_ONLY_SEED_HEX.encode() not in blob
    assert TEST_ONLY_SEED_HEX.upper().encode() not in blob
    assert TEST_ONLY_VAULT_PASSPHRASE.encode() not in blob


@windows_only
def test_vault_envelope_is_versioned_and_strict(vault: DpapiVault) -> None:
    identity_id = new_identity_id()
    path = vault.store(
        identity_id=identity_id,
        seed=TEST_ONLY_SEED,
        protection=ProtectionMode.DPAPI,
        passphrase=None,
    )
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["format"] == "technocore-station.vault"
    assert envelope["version"] == 1
    assert set(envelope) == {
        "format",
        "version",
        "identity_id",
        "protection",
        "created_at",
        "dpapi_blob",
    }

    # An unknown field must be refused, not ignored.
    envelope["extra"] = "x"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultFormatError):
        vault.load(identity_id=identity_id)


@windows_only
def test_wrong_passphrase_and_tamper_share_one_error(vault: DpapiVault) -> None:
    identity_id = new_identity_id()
    path = vault.store(
        identity_id=identity_id,
        seed=TEST_ONLY_SEED,
        protection=ProtectionMode.DPAPI_PASSPHRASE,
        passphrase=TEST_ONLY_VAULT_PASSPHRASE,
    )

    with pytest.raises(VaultUnlockError):
        vault.load(identity_id=identity_id, passphrase=TEST_ONLY_WRONG_PASSPHRASE)

    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["dpapi_blob"] = envelope["dpapi_blob"][:-4] + "AAAA"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultUnlockError):
        vault.load(identity_id=identity_id, passphrase=TEST_ONLY_VAULT_PASSPHRASE)


@windows_only
def test_vault_never_overwrites_and_deletes_cleanly(vault: DpapiVault) -> None:
    identity_id = new_identity_id()
    vault.store(
        identity_id=identity_id,
        seed=TEST_ONLY_SEED,
        protection=ProtectionMode.DPAPI,
        passphrase=None,
    )
    with pytest.raises(VaultAlreadyExistsError):
        vault.store(
            identity_id=identity_id,
            seed=TEST_ONLY_SEED,
            protection=ProtectionMode.DPAPI,
            passphrase=None,
        )

    assert vault.delete(identity_id) is True
    assert vault.exists(identity_id) is False
    with pytest.raises(VaultNotFoundError):
        vault.load(identity_id=identity_id)


@windows_only
def test_atomic_write_leaves_no_temporary_file(vault: DpapiVault, tmp_path: Path) -> None:
    identity_id = new_identity_id()
    vault.store(
        identity_id=identity_id,
        seed=TEST_ONLY_SEED,
        protection=ProtectionMode.DPAPI,
        passphrase=None,
    )
    leftovers = list((tmp_path / "vault" / "v1").glob("*.tmp"))
    assert leftovers == [], f"temporary vault files survived: {leftovers}"


@windows_only
def test_acl_is_restricted_to_the_current_user_and_system(vault: DpapiVault) -> None:
    """Read the DACL back and prove only two principals are granted."""
    from station_api.vault.windows_acl import (
        acl_grantee_sids,
        current_user_sid,
        describe_acl,
    )

    identity_id = new_identity_id()
    path = vault.store(
        identity_id=identity_id,
        seed=TEST_ONLY_SEED,
        protection=ProtectionMode.DPAPI,
        passphrase=None,
    )

    sddl = describe_acl(path)
    assert sddl.startswith("D:P"), f"DACL is not protected against inheritance: {sddl}"

    granted = [entry for entry in sddl.split("(") if entry.startswith("A;")]
    assert len(granted) == 2, f"expected exactly two allow ACEs, got {sddl}"

    # Compare the real trustee SIDs, not SDDL text: SDDL abbreviates
    # well-known accounts (the built-in Administrator renders as `LA`, not as
    # its S-1-5-21-...-500 string), so a substring check would fail on such
    # accounts even though the ACL is exactly right - and, worse, could pass
    # on text that does not mean what it looks like. Exact set equality on
    # resolved SIDs is the stronger claim: SYSTEM and the current user, and
    # nobody else.
    assert sorted(acl_grantee_sids(path)) == sorted(("S-1-5-18", current_user_sid()))


def test_identity_id_cannot_traverse_the_filesystem(vault: DpapiVault) -> None:
    for hostile in ("../escape", "a" * 31, "", "../../etc/passwd"):
        with pytest.raises(VaultFormatError):
            vault.path_for(hostile)


# --- recovery --------------------------------------------------------------


def test_recovery_round_trip_reproduces_the_did(fast_kdf_policy: KdfPolicy) -> None:
    payload = create_recovery(
        seed=TEST_ONLY_SEED,
        passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
        policy=fast_kdf_policy,
    )
    opened = open_recovery(
        payload, passphrase=TEST_ONLY_RECOVERY_PASSPHRASE, policy=fast_kdf_policy
    )
    assert opened.seed == TEST_ONLY_SEED
    assert opened.did == did_key_from_seed(TEST_ONLY_SEED)


def test_two_exports_use_a_fresh_salt_and_nonce(fast_kdf_policy: KdfPolicy) -> None:
    first = create_recovery(
        seed=TEST_ONLY_SEED,
        passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
        policy=fast_kdf_policy,
    )
    second = create_recovery(
        seed=TEST_ONLY_SEED,
        passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
        policy=fast_kdf_policy,
    )

    assert first != second
    a, b = json.loads(first), json.loads(second)
    assert a["salt"] != b["salt"]
    assert a["nonce"] != b["nonce"]
    assert a["ciphertext"] != b["ciphertext"]
    assert file_fingerprint(first) != file_fingerprint(second)


def test_recovery_file_contains_no_plaintext_seed(fast_kdf_policy: KdfPolicy) -> None:
    payload = create_recovery(
        seed=TEST_ONLY_SEED,
        passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
        policy=fast_kdf_policy,
    )
    assert TEST_ONLY_SEED not in payload
    assert TEST_ONLY_SEED_HEX.encode() not in payload
    assert TEST_ONLY_RECOVERY_PASSPHRASE.encode() not in payload


def _tamper(payload: bytes, key: str, value: object) -> bytes:
    header = json.loads(payload)
    header[key] = value
    return canonical_json_bytes(header)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("did", "did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp"),
        ("created_at", "1999-01-01T00:00:00+00:00"),
        ("kdf_time_cost", 4),
        ("kdf_parallelism", 2),
    ],
)
def test_authenticated_header_tampering_is_refused(
    fast_kdf_policy: KdfPolicy, key: str, value: object
) -> None:
    """Every header field except ciphertext is AAD, so editing one breaks it."""
    payload = create_recovery(
        seed=TEST_ONLY_SEED,
        passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
        policy=fast_kdf_policy,
    )
    with pytest.raises(VaultUnlockError):
        open_recovery(
            _tamper(payload, key, value),
            passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
            policy=fast_kdf_policy,
        )


def test_wrong_passphrase_and_ciphertext_tamper_share_one_contract(
    fast_kdf_policy: KdfPolicy,
) -> None:
    payload = create_recovery(
        seed=TEST_ONLY_SEED,
        passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
        policy=fast_kdf_policy,
    )

    with pytest.raises(VaultUnlockError):
        open_recovery(payload, passphrase=TEST_ONLY_WRONG_PASSPHRASE, policy=fast_kdf_policy)

    header = json.loads(payload)
    header["ciphertext"] = header["ciphertext"][:-4] + "AAAA"
    with pytest.raises(VaultUnlockError):
        open_recovery(
            canonical_json_bytes(header),
            passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
            policy=fast_kdf_policy,
        )


def test_aad_v1_is_byte_exact() -> None:
    """Pin the AAD canonicalization with a fixed vector.

    Keys sorted by code point, separators ',' and ':' with no whitespace,
    non-ASCII preserved, UTF-8. ``ciphertext`` is excluded.
    """
    header = {
        "format": "technocore-station.recovery",
        "version": 1,
        "did": "did:key:zTEST",
        "created_at": "2026-08-30T00:00:00+00:00",
        "kdf": "argon2id",
        "kdf_time_cost": 3,
        "kdf_memory_kib": 65536,
        "kdf_parallelism": 1,
        "salt": "AAAA",
        "aead": "chacha20poly1305",
        "nonce": "BBBB",
        "ciphertext": "SHOULD-NOT-APPEAR",
    }
    expected = (
        b'{"aead":"chacha20poly1305","created_at":"2026-08-30T00:00:00+00:00",'
        b'"did":"did:key:zTEST","format":"technocore-station.recovery",'
        b'"kdf":"argon2id","kdf_memory_kib":65536,"kdf_parallelism":1,'
        b'"kdf_time_cost":3,"nonce":"BBBB","salt":"AAAA","version":1}'
    )
    assert aad_for_header(header) == expected
    assert b"SHOULD-NOT-APPEAR" not in aad_for_header(header)


def test_non_ascii_is_preserved_in_the_aad() -> None:
    """ensure_ascii=false: a Turkish character must not become an escape."""
    assert "ş".encode() in aad_for_header({"label": "şifre", "ciphertext": "x"})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("version", 2),
        ("format", "something-else"),
        ("kdf", "scrypt"),
        ("aead", "aes-gcm"),
    ],
)
def test_unsupported_version_or_algorithm_is_refused(
    fast_kdf_policy: KdfPolicy, key: str, value: object
) -> None:
    payload = create_recovery(
        seed=TEST_ONLY_SEED,
        passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
        policy=fast_kdf_policy,
    )
    with pytest.raises(VaultUnlockError):
        open_recovery(
            _tamper(payload, key, value),
            passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
            policy=fast_kdf_policy,
        )


def test_duplicate_keys_are_refused(fast_kdf_policy: KdfPolicy) -> None:
    payload = create_recovery(
        seed=TEST_ONLY_SEED,
        passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
        policy=fast_kdf_policy,
    )
    doubled = b'{"version":1,' + payload[1:]
    with pytest.raises(VaultUnlockError):
        open_recovery(doubled, passphrase=TEST_ONLY_RECOVERY_PASSPHRASE, policy=fast_kdf_policy)


def test_oversized_recovery_file_is_refused(fast_kdf_policy: KdfPolicy) -> None:
    with pytest.raises(VaultUnlockError):
        open_recovery(
            b'{"x":"' + b"A" * 70_000 + b'"}',
            passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
            policy=fast_kdf_policy,
        )


def test_padded_base64url_is_refused(fast_kdf_policy: KdfPolicy) -> None:
    """The encoding decision is unpadded base64url, and it is enforced."""
    payload = create_recovery(
        seed=TEST_ONLY_SEED,
        passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
        policy=fast_kdf_policy,
    )
    header = json.loads(payload)
    header["salt"] = header["salt"] + "="
    with pytest.raises(VaultUnlockError):
        open_recovery(
            canonical_json_bytes(header),
            passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
            policy=fast_kdf_policy,
        )


def test_production_policy_refuses_cheap_test_parameters() -> None:
    """A file built with test-grade KDF cost must not open in production.

    This is what keeps the injectable policy from becoming a downgrade path.
    """
    cheap = KdfPolicy(time_cost=1, memory_cost_kib=8, min_time_cost=1, min_memory_cost_kib=8)
    payload = create_recovery(
        seed=TEST_ONLY_SEED, passphrase=TEST_ONLY_RECOVERY_PASSPHRASE, policy=cheap
    )

    with pytest.raises(VaultUnlockError):
        open_recovery(
            payload,
            passphrase=TEST_ONLY_RECOVERY_PASSPHRASE,
            policy=PRODUCTION_KDF_POLICY,
        )


def test_production_policy_matches_the_documented_values() -> None:
    assert PRODUCTION_KDF_POLICY.memory_cost_kib == 65536  # 64 MiB
    assert PRODUCTION_KDF_POLICY.time_cost == 3
    assert PRODUCTION_KDF_POLICY.parallelism == 1
    assert PRODUCTION_KDF_POLICY.hash_length == 32
