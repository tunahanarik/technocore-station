"""Shared fixtures.

No test in this suite contacts the real Technocore. There is no outbound
network client in the product yet, and INV-05 forbids adding one to a test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


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
