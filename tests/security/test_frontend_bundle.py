"""SI-24, SI-37, SI-44 .. SI-47 - what the shipped frontend may contain.

These read the production build. If it is missing, the test fails with the
command to produce it rather than skipping: a silently skipped security test
is indistinguishable from a passing one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.security

BUILD_COMMAND = "npm --prefix apps/station-web run build"

#: Any host:port pair that would pin the frontend to a fixed backend port.
HARDCODED_PORT_RE = re.compile(r"(?:127\.0\.0\.1|localhost|0\.0\.0\.0):\d{2,5}")

REMOTE_ASSET_MARKERS = (
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "cdn.jsdelivr.net",
    "unpkg.com",
    "cdnjs.cloudflare.com",
)

BROWSER_STORAGE_MARKERS = ("localStorage", "sessionStorage", "indexedDB")


def _require_build(web_dist_root: Path) -> Path:
    index = web_dist_root / "index.html"
    if not index.is_file():
        pytest.fail(f"production build missing at {web_dist_root}. Run: {BUILD_COMMAND}")
    return index


def _bundle_files(web_dist_root: Path) -> list[Path]:
    return [
        path
        for path in web_dist_root.rglob("*")
        if path.is_file() and path.suffix in {".js", ".css", ".html", ".mjs"}
    ]


def test_production_build_output_exists(web_dist_root: Path) -> None:
    index = _require_build(web_dist_root)
    assert index.stat().st_size > 0

    scripts = list(web_dist_root.rglob("*.js"))
    assert scripts, "the build produced no JavaScript"


def test_no_hardcoded_backend_port_in_bundle(web_dist_root: Path) -> None:
    """The SPA is served from the API origin and uses relative URLs only."""
    _require_build(web_dist_root)
    offenders: list[str] = []

    for path in _bundle_files(web_dist_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in HARDCODED_PORT_RE.findall(text):
            offenders.append(f"{path.name}: {match}")

    assert offenders == [], f"hardcoded backend address in bundle: {offenders}"


def test_frontend_source_uses_relative_api_urls(web_source_root: Path) -> None:
    offenders: list[str] = []
    for path in web_source_root.rglob("*.ts*"):
        if path.name.endswith((".test.ts", ".test.tsx")):
            continue
        text = path.read_text(encoding="utf-8")
        for match in HARDCODED_PORT_RE.findall(text):
            offenders.append(f"{path.name}: {match}")

    assert offenders == [], f"hardcoded backend address in source: {offenders}"


def _strip_ts_comments(source: str) -> str:
    """Remove comments so prose about the rule cannot trip the rule.

    A comment stating that storage is never used is exactly what we want the
    code to say; only executable code is scanned below.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", without_blocks)


def test_no_browser_storage_for_csrf(web_source_root: Path) -> None:
    """The CSRF value lives in memory. No storage API is used at all."""
    offenders: list[str] = []
    for path in web_source_root.rglob("*.ts*"):
        if path.name.endswith((".test.ts", ".test.tsx")):
            continue
        code = _strip_ts_comments(path.read_text(encoding="utf-8"))
        for marker in BROWSER_STORAGE_MARKERS:
            if marker in code:
                offenders.append(f"{path.name}: {marker}")

    assert offenders == [], f"browser storage used in frontend source: {offenders}"


def test_the_storage_scanner_would_catch_a_real_violation() -> None:
    """Guards the guard: stripping comments must not blind the check."""
    assert "localStorage" not in _strip_ts_comments("// uses localStorage\n")
    assert "localStorage" in _strip_ts_comments('localStorage.setItem("k", v);\n')


def test_no_remote_asset_references(web_dist_root: Path) -> None:
    """No Google Fonts, no CDN: the CSP would block them and they leak."""
    _require_build(web_dist_root)
    offenders: list[str] = []

    for path in _bundle_files(web_dist_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in REMOTE_ASSET_MARKERS:
            if marker in text:
                offenders.append(f"{path.name}: {marker}")

    assert offenders == [], f"remote asset reference in bundle: {offenders}"


def test_no_inline_script_in_index_html(web_dist_root: Path) -> None:
    """script-src 'self' blocks inline script, so the build must emit none."""
    index = _require_build(web_dist_root)
    html = index.read_text(encoding="utf-8")

    inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html, flags=re.IGNORECASE)
    assert inline_scripts == [], f"inline script in index.html: {inline_scripts}"


def test_no_heroui_v2_or_nextui_dependency(repo_root: Path) -> None:
    manifest = json.loads(
        (repo_root / "apps" / "station-web" / "package.json").read_text(encoding="utf-8")
    )
    dependencies: dict[str, str] = {
        **manifest.get("dependencies", {}),
        **manifest.get("devDependencies", {}),
    }

    for name in dependencies:
        assert not name.startswith("@nextui-org/"), f"NextUI dependency found: {name}"
        assert name != "nextui", "NextUI dependency found"

    # HeroUI must be v3. A v2 range would start with 2.
    for package in ("@heroui/react", "@heroui/styles"):
        spec = dependencies.get(package)
        assert spec is not None, f"{package} is required"
        assert re.match(r"^[\^~]?3\.", spec), f"{package} must be v3, found {spec}"


def test_installed_heroui_is_v3(repo_root: Path) -> None:
    """The resolved install, not just the declared range."""
    installed = (
        repo_root
        / "apps"
        / "station-web"
        / "node_modules"
        / "@heroui"
        / "react"
        / "package.json"
    )
    if not installed.is_file():
        pytest.fail(
            "frontend dependencies are not installed. "
            "Run: npm --prefix apps/station-web install"
        )

    version = str(json.loads(installed.read_text(encoding="utf-8"))["version"])
    assert version.startswith("3."), f"HeroUI v3 required, found {version}"


def test_no_nextui_in_the_installed_tree(repo_root: Path) -> None:
    nextui_dir = repo_root / "apps" / "station-web" / "node_modules" / "@nextui-org"
    assert not nextui_dir.exists(), "NextUI is installed; HeroUI v2 patterns are banned"
