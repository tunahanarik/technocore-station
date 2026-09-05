"""SI-24, SI-37, SI-44 .. SI-47 - what the shipped frontend may contain.

These read the production build. If it is missing, the test fails with the
command to produce it rather than skipping: a silently skipped security test
is indistinguishable from a passing one.

ADR-0010 4 adds the question these six audits could not answer on their own:
**are the bytes they read the bytes that ship?** They read
``apps/station-web/dist``. Package I copies the SPA into a PyInstaller
bundle, and the moment a copy exists the six become an audit of a directory
the user never receives - they do not go red, they simply stop looking at
anything, which is the failure shape this repository has caught repeatedly
since ADR-0004. So one assertion carries all six across: the shipped copy is
byte-for-byte the audited ``dist``, and the packaging spec is checked to be
copying from ``dist`` and nowhere else.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from station_api.resources import BUNDLED_WEB_DIR

pytestmark = pytest.mark.security

BUILD_COMMAND = "npm --prefix apps/station-web run build"

#: Where ``packaging/build_bundle.py`` leaves the onedir bundle, and where
#: PyInstaller puts a onedir build's data files inside it.
BUNDLE_ROOT_PARTS = ("packaging", "artifacts", "bundle", "TechnocoreStation")
BUNDLE_INTERNAL = "_internal"

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


# ---------------------------------------------------------------------------
# ADR-0010 4: the audited dist and the shipped dist are the same bytes
# ---------------------------------------------------------------------------


def _tree_digests(root: Path) -> dict[str, str]:
    """Every file under ``root``, as relative path -> SHA-256 of its bytes.

    A map rather than a single rolled-up number on purpose: when it differs,
    the assertion names the file that differs instead of reporting that two
    hex strings are not equal.
    """
    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            digests[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def _shipped_spa_root(repo_root: Path) -> Path | None:
    """The SPA copy inside a built bundle, or ``None`` if none was built."""
    candidate = repo_root.joinpath(*BUNDLE_ROOT_PARTS, BUNDLE_INTERNAL, BUNDLED_WEB_DIR)
    return candidate if (candidate / "index.html").is_file() else None


def test_the_byte_identity_comparison_reports_a_single_changed_byte(
    tmp_path: Path,
) -> None:
    """Guards the guard, at the resolution the rule claims.

    "Byte-for-byte" is a strong phrase and a comparison that only looked at
    file names would satisfy it in wording and not in fact. So the driver
    changes one byte of one file in an otherwise identical copy and requires
    that exact file to be the one reported, and separately drops a file to
    prove an omission is caught too.
    """
    audited = tmp_path / "audited"
    (audited / "assets").mkdir(parents=True)
    (audited / "index.html").write_text("<!doctype html><body>a</body>", encoding="utf-8")
    (audited / "assets" / "app.js").write_text("export const a = 1;\n", encoding="utf-8")

    identical = tmp_path / "identical"
    identical.mkdir()
    (identical / "assets").mkdir()
    (identical / "index.html").write_bytes((audited / "index.html").read_bytes())
    (identical / "assets" / "app.js").write_bytes(
        (audited / "assets" / "app.js").read_bytes()
    )
    assert _tree_digests(identical) == _tree_digests(audited)

    (identical / "assets" / "app.js").write_text("export const a = 2;\n", encoding="utf-8")
    changed = _tree_digests(identical)
    original = _tree_digests(audited)
    assert changed != original
    differing = {name for name in original if changed.get(name) != original[name]}
    assert differing == {"assets/app.js"}

    (identical / "assets" / "app.js").unlink()
    assert set(_tree_digests(identical)) != set(original)


def test_the_packaging_spec_ships_the_audited_dist_and_nothing_else(
    repo_root: Path,
) -> None:
    """The copy's *source* is pinned, so it cannot quietly become another tree.

    Without this, the byte-identity check below could be satisfied by
    pointing both the audits and the packager at some third directory.
    """
    spec = (repo_root / "packaging" / "station.spec").read_text(encoding="utf-8")

    assert 'WEB_DIST_SOURCE = os.path.join(REPO_ROOT, "apps", "station-web", "dist")' in spec
    assert f'WEB_DIST_TARGET = "{BUNDLED_WEB_DIR}"' in spec
    assert "(WEB_DIST_SOURCE, WEB_DIST_TARGET)" in spec


def test_the_shipped_spa_is_byte_for_byte_the_audited_dist(
    repo_root: Path, web_dist_root: Path
) -> None:
    """ADR-0010 4. One assertion, carrying six audits onto the shipped bytes.

    When no bundle has been built this cannot compare anything, and it says
    which of the two possible reasons applies rather than passing quietly: a
    bundle that exists but whose SPA is somewhere else is a *failure* here,
    because that is precisely the state in which the six audits above are
    reading a directory nobody receives.
    """
    _require_build(web_dist_root)
    shipped = _shipped_spa_root(repo_root)

    if shipped is None:
        bundle_root = repo_root.joinpath(*BUNDLE_ROOT_PARTS)
        assert not bundle_root.exists(), (
            f"a bundle exists at {bundle_root} but carries no SPA at "
            f"{BUNDLE_INTERNAL}/{BUNDLED_WEB_DIR}; the audits in this file are "
            "then inspecting bytes that are not the ones shipped"
        )
        return

    audited = _tree_digests(web_dist_root)
    assert len(audited) > 2, "the audited dist is implausibly small"
    assert _tree_digests(shipped) == audited


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
