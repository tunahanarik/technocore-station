"""Shared fixtures.

No test in this suite contacts the real Technocore. There is no outbound
network client in the product yet, and INV-05 forbids adding one to a test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine
from station_api.config import Settings
from station_api.db.migrations_runner import initialise_database

REPO_ROOT = Path(__file__).resolve().parents[1]

#: A fixed, plausible ephemeral port. The app only ever compares it against
#: the Host header; nothing binds it during these tests.
TEST_PORT = 49731


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def api_source_root(repo_root: Path) -> Path:
    return repo_root / "apps" / "station-api" / "src"


@pytest.fixture(scope="session")
def web_source_root(repo_root: Path) -> Path:
    return repo_root / "apps" / "station-web" / "src"


@pytest.fixture(scope="session")
def web_dist_root(repo_root: Path) -> Path:
    return repo_root / "apps" / "station-web" / "dist"


# ---------------------------------------------------------------------------
# TEST-ONLY key material.
#
# Every value below is a fixture, published in this repository, and must never
# be used for anything real. The leak-detection marker seed is deliberately
# unusual so a substring search for it is meaningful.
# ---------------------------------------------------------------------------

#: TEST-ONLY. NOT A REAL SEED.
TEST_ONLY_SEED_HEX = "4c7a1e9b3d5f8027a6c4e91b2d8f0356749ace1b2d4f6081a3c5e7092b4d6f81"

#: TEST-ONLY. A second fixture seed, for differential coverage.
TEST_ONLY_SEED_HEX_ALT = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"

#: TEST-ONLY passphrases. NOT REAL.
TEST_ONLY_VAULT_PASSPHRASE = "TEST-ONLY-vault-passphrase-0001"
TEST_ONLY_RECOVERY_PASSPHRASE = "TEST-ONLY-recovery-passphrase-01"
TEST_ONLY_WRONG_PASSPHRASE = "TEST-ONLY-wrong-passphrase-9999"


@pytest.fixture(scope="session")
def test_only_seed() -> bytes:
    return bytes.fromhex(TEST_ONLY_SEED_HEX)


# ---------------------------------------------------------------------------
# Application fixtures, shared by the security and integration packages.
# ---------------------------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "station-data"


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    """Production settings. Development mode is off, as it is by default."""
    return Settings(dev_mode=False, data_dir=data_dir)


@pytest.fixture
def dev_settings(data_dir: Path) -> Settings:
    return Settings(dev_mode=True, data_dir=data_dir)


@pytest.fixture
def engine(settings: Settings) -> Engine:
    return initialise_database(settings.database_path, stage=2)


@pytest.fixture
def base_url() -> str:
    return f"http://127.0.0.1:{TEST_PORT}"


@pytest.fixture
def fast_kdf_policy():  # type: ignore[no-untyped-def]
    """A cheap Argon2id policy so unit tests are not dominated by the KDF.

    Injected into the *library*; production endpoints always construct
    ``PRODUCTION_KDF_POLICY`` and its accept-bounds refuse these parameters,
    which is asserted in tests/security/test_identity_vault.py.
    """
    from station_api.vault.passphrase import KdfPolicy

    return KdfPolicy(
        time_cost=1,
        memory_cost_kib=8,
        parallelism=1,
        min_time_cost=1,
        max_time_cost=10,
        min_memory_cost_kib=8,
        max_memory_cost_kib=262144,
    )
