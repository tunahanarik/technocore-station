"""The workspace, and the ways out of it that are closed.

ADR-0008 5 notes that there was **no precedent** for this in the repository.
Station hands files to the browser rather than writing to a path a user chose
(``downloads.py``), the vault writes one file it names itself, and neither
ever faced traversal, a symbolic link or an archive. Nothing here is a
re-statement of an existing control; every assertion below is about code that
was written from nothing, which is exactly why it is tested as hostilely as
the suite knows how.

Four layers, tested as four
---------------------------
1. **the name is rebuilt, not filtered.** Everything outside
   ``[A-Za-z0-9._-]`` is gone, and a name that would have been *rewritten* is
   **refused** instead. That refusal is the interesting decision: a download
   header may rename freely, but a run goes on to hash the file it named, and
   a silent rename makes that comparison be about a different file.
2. **resolve then contain.** ``resolve()`` and
   ``is_relative_to(root.resolve())`` on every read and every write.
3. **reparse points refused, all the way up.** ``is_symlink()`` *and*
   ``os.path.isjunction()``, on the file and on every directory between it and
   the root. The second predicate is the one a POSIX habit would omit, and an
   NTFS junction is the reparse point an unprivileged Windows user can
   actually create.
4. **ceilings, read from disk.** File count, per-file bytes and total bytes,
   checked against the directory as it is rather than against a counter the
   runner keeps - a counter and a directory can disagree, and only one of them
   is what the user has.

And a fifth thing that is an absence rather than a layer: **there is no
archive path**, so zip-slip has no surface. That is asserted in
``test_agent_boundary.py``, where the import scan lives.

On testing links, and the sentence that used to be here
--------------------------------------------------------
This docstring used to say that creating an NTFS junction "needs a subprocess
this package is forbidden to spawn". That was wrong twice over, and an
independent review measured both halves: the ban on ``subprocess`` is on the
**product source**, not on a test, and ``mklink /J`` creates a junction on
this machine **without administrator rights**. The consequence was that layer
3 had never once been driven by a real reparse point - both tests that killed
it forced ``os.path.isjunction`` through ``monkeypatch`` - and a guard only
ever shown a forced predicate had not been shown to defend anything. It did
not: the walk ran on the ``resolve()``d path, which by definition has no
links left in it, and a junction planted on the workspace directory was read
straight through.

So :func:`_plant_a_real_reparse_point` plants a real one - a symbolic link
where the OS allows it, an NTFS junction where it does not - and the tests
below assert the refusal against it. A machine that can create neither falls
back to the forced predicate, in the same test, with no ``skip``:
``tests/security`` may not skip, and a machine that cannot plant a link still
has to drive the guard.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from station_api.agent import workspace as workspace_module
from station_api.agent.errors import WorkspaceError
from station_api.agent.workspace import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    digest_of,
    ensure_workspace,
    list_files,
    read_text,
    resolve_within,
    safe_name,
    task_workspace,
    total_bytes,
    validate_task_id,
    workspace_root,
    write_text,
)
from station_api.vault.windows_acl import acl_grantee_sids, current_user_sid, is_windows

pytestmark = pytest.mark.security

TEST_ONLY_TASK_ID = "0123456789abcdef0123456789abcdef"

#: Names that must never become a path. Every one of them is a real attempt
#: somebody would make, spelled the way Windows and POSIX each accept.
HOSTILE_NAMES = (
    "../escape.txt",
    "..\\escape.txt",
    "../../../../Windows/System32/drivers/etc/hosts",
    "..%2fescape.txt",
    "sub/dir.txt",
    "sub\\dir.txt",
    "C:\\Windows\\win.ini",
    "\\\\server\\share\\file.txt",
    "/etc/passwd",
    "..",
    ".",
    "con.json",
    "rapor\x00.txt",
    "rapor\r\n.txt",
    "rapor\u202e.txt",
)


#: A second application-generated id, for the tests that need a workspace
#: directory ``ensure_workspace`` has not created yet.
TEST_ONLY_OTHER_TASK_ID = "fedcba9876543210fedcba9876543210"

#: ``mklink``'s host. Read from the environment rather than spelled, and with
#: the documented default when it is unset.
_COMSPEC = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")


def _plant_a_real_reparse_point(link: Path, target: Path) -> bool:
    """Create a real link at ``link`` pointing at ``target``; say whether it worked.

    A symbolic link first, because it is the one the standard library can
    make. Where Windows refuses it - developer mode off, which is the common
    case for this product's users - an NTFS junction is created with
    ``mklink /J``, which needs no administrator right. The measurement that
    made this function necessary is in this module's docstring.

    ``subprocess`` is forbidden in the **product source**, where
    ``test_agent_boundary.py`` reads the syntax tree to say so. A test may
    spawn one, and several in ``tests/conformance`` already do.
    """
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pass
    else:
        return True

    if sys.platform != "win32" or not target.is_dir():
        return False
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, tmp_path operands
        [_COMSPEC, "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    # Asserted rather than inferred from the exit code: a reparse point the
    # predicate does not recognise would not be driving the guard.
    return result.returncode == 0 and os.path.isjunction(link)


@pytest.fixture
def root(data_dir: Path) -> Path:
    return ensure_workspace(data_dir, TEST_ONLY_TASK_ID)


# ---------------------------------------------------------------------------
# The address is the application's, never a request's
# ---------------------------------------------------------------------------


def test_the_workspace_is_versioned_under_the_data_directory(data_dir: Path) -> None:
    """``vault/paths.py``'s shape, and it buys a test for free.

    Living under the data root means the seed scan - which reads *every* file
    there - covers workspace files automatically, rather than by somebody
    remembering to add a path to it.
    """
    directory = task_workspace(data_dir, TEST_ONLY_TASK_ID)

    assert directory.parent == workspace_root(data_dir)
    assert directory.parent.name == "v1"
    assert directory.parent.parent.name == "workspace"
    assert directory.is_relative_to(data_dir)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "../../etc",
        "0123456789ABCDEF0123456789ABCDEF",
        "0123456789abcdef0123456789abcde",
        "0123456789abcdef0123456789abcdefa",
        "0123456789abcdef0123456789abcde/",
    ],
)
def test_a_task_id_that_is_not_an_application_identifier_never_becomes_a_path(
    bad: str,
) -> None:
    with pytest.raises(WorkspaceError) as caught:
        validate_task_id(bad)

    assert caught.value.reason == "workspace_id_invalid"


def test_a_hand_built_workspace_path_is_refused_before_it_is_a_path(
    data_dir: Path,
) -> None:
    with pytest.raises(WorkspaceError):
        task_workspace(data_dir, "../../../Windows")


# ---------------------------------------------------------------------------
# Layer 1: the name is rebuilt, and a rewrite is a refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hostile", HOSTILE_NAMES)
def test_a_name_carrying_syntax_is_refused_rather_than_rewritten(
    hostile: str,
) -> None:
    """Refused, not sanitised into something else.

    ``downloads.safe_download_filename`` would happily turn ``a/b.txt`` into
    ``a-b.txt``, and for a save dialog that is right. Here it is wrong: the
    run hashes the file it named, so a silent rename makes the later digest
    check be about a different file than the plan promised.
    """
    with pytest.raises(WorkspaceError) as caught:
        safe_name(hostile)

    assert caught.value.reason == "workspace_name_refused"


@pytest.mark.parametrize(
    "good", ["rapor.json", "notlar.md", "a-b_c.txt", "patch.diff", "v1.2.3.txt"]
)
def test_an_ordinary_name_survives_unchanged(good: str) -> None:
    assert safe_name(good) == good


def test_a_name_that_reduces_to_a_directory_is_refused(root: Path) -> None:
    with pytest.raises(WorkspaceError):
        resolve_within(root, "..")


# ---------------------------------------------------------------------------
# Layer 2: resolve and contain
# ---------------------------------------------------------------------------


def test_every_resolved_name_stays_inside_the_workspace(root: Path) -> None:
    resolved = resolve_within(root, "rapor.json")

    assert resolved.is_relative_to(root.resolve())
    assert resolved.parent == root.resolve()


def test_the_containment_check_refuses_a_path_that_leaves_the_root(
    data_dir: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second layer, driven on its own - and this test used to not do that.

    The previous version called ``read_text(root, "../escape.txt")`` and said
    in its own docstring that the only way to exercise layer 2 is to reach
    past layer 1. It did not reach past layer 1: ``safe_name`` refused that
    name and containment was never consulted, so deleting the containment
    check left the whole suite green. An independent review measured it -
    ``if not candidate.is_relative_to(resolved_root)`` turned into
    ``if False``, zero failures.

    So layer 1 is actually neutralised here, which is the shape a refactor
    that loosened the name rule would take, and then containment is required
    to refuse on its own.
    """
    outside = (data_dir / "escape.txt").resolve()
    assert not outside.is_relative_to(root.resolve())

    monkeypatch.setattr(workspace_module, "safe_name", lambda raw: raw)

    with pytest.raises(WorkspaceError) as caught:
        resolve_within(root, "../escape.txt")

    assert caught.value.reason == "workspace_escape"


def test_containment_refuses_a_real_link_that_leaves_the_root(
    data_dir: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Layer 2 again, this time without touching layer 1 at all.

    A real reparse point inside the workspace whose target is outside it is
    the case where an *allowed* name resolves out of the root, and it needs
    no monkeypatch to construct: ``safe_name`` is happy with ``disari``, and
    it is ``resolve()`` that lands the path somewhere else.

    Layer 3 refuses this too, and deliberately earlier - ``read_text`` walks
    the unresolved path first. ``resolve_within`` is called directly here so
    the containment check answers for itself.
    """
    outside = data_dir / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "gizli.txt").write_text("TEST-ONLY disarida", encoding="utf-8")
    link = root / "disari"

    if _plant_a_real_reparse_point(link, outside):
        try:
            with pytest.raises(WorkspaceError) as real:
                resolve_within(root.resolve(), "disari")
            assert real.value.reason == "workspace_escape"
        finally:
            link.rmdir()

    # And on a machine that can plant neither, layer 1 is neutralised so the
    # containment check is still driven. No skip: this file may not have one.
    monkeypatch.setattr(workspace_module, "safe_name", lambda raw: raw)

    with pytest.raises(WorkspaceError) as forced:
        resolve_within(root, "../../escape.txt")

    assert forced.value.reason == "workspace_escape"


def test_two_tasks_cannot_reach_each_other(data_dir: Path) -> None:
    other_id = "fedcba9876543210fedcba9876543210"
    mine = ensure_workspace(data_dir, TEST_ONLY_TASK_ID)
    theirs = ensure_workspace(data_dir, other_id)
    write_text(theirs, "gizli.md", "TEST-ONLY baska gorevin dosyasi", replace_existing=False)

    with pytest.raises(WorkspaceError):
        read_text(mine, f"../{other_id}/gizli.md")

    assert [item.name for item in list_files(mine)] == []


# ---------------------------------------------------------------------------
# Layer 3: reparse points
# ---------------------------------------------------------------------------


def test_a_link_inside_the_workspace_is_refused(
    root: Path, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Driven two ways, so no machine skips it.

    A real symbolic link is attempted first: where the OS allows it, the
    refusal is exercised against an actual reparse point. Where it does not -
    Windows without developer mode, which is the common case for this
    product's users - the predicate is forced on a real path instead, so the
    guard is still driven rather than assumed.
    """
    target = data_dir / "outside.txt"
    target.write_text("TEST-ONLY disarida", encoding="utf-8")
    link = root / "link.txt"

    created = True
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        created = False

    if created:
        with pytest.raises(WorkspaceError) as caught:
            read_text(root, "link.txt")
        assert caught.value.reason == "workspace_reparse_point"
        link.unlink()

    # The forced half. ``isjunction`` is the predicate a POSIX habit omits,
    # and it is the one that matters on the platform this product ships on.
    monkeypatch.setattr(os.path, "isjunction", lambda _path: True)
    write_target = root / "rapor.md"
    write_target.write_text("TEST-ONLY", encoding="utf-8")

    with pytest.raises(WorkspaceError) as forced:
        read_text(root, "rapor.md")

    assert forced.value.reason == "workspace_reparse_point"


def test_a_link_above_the_file_is_refused_too(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The walk goes upwards, because a link one level up redirects just as well.

    Checking only the leaf would leave the case where the *workspace
    directory* is the reparse point, which is the more useful one to plant.
    """
    write_text(root, "rapor.md", "TEST-ONLY", replace_existing=False)
    seen: list[Path] = []

    def _fake(path: str | os.PathLike[str]) -> bool:
        seen.append(Path(path))
        return Path(path) == root.resolve()

    monkeypatch.setattr(os.path, "isjunction", _fake)

    with pytest.raises(WorkspaceError) as caught:
        read_text(root, "rapor.md")

    assert caught.value.reason == "workspace_reparse_point"
    assert root.resolve() in seen


def test_a_real_reparse_point_on_the_workspace_directory_is_refused(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measurement that produced this test, and what it found.

    A junction planted on the **task directory itself** was read straight
    through: ``isjunction`` said ``True`` about it, ``read_text`` returned the
    canary from the other side of it, ``list_files`` listed the other side's
    files and ``ensure_workspace`` accepted it without a word. The cause was
    that every call site handed the walk a ``resolve()``d path, and
    ``resolve()`` dissolves a junction - so no component the walk looked at
    was ever a link.

    This is the test that was missing: a real reparse point, refused by the
    reparse layer, by reason. Deleting the unresolved walk turns it red,
    which is the property the two ``monkeypatch``ed tests beside it never had.
    """
    elsewhere = data_dir / "elsewhere"
    elsewhere.mkdir(parents=True, exist_ok=True)
    (elsewhere / "rapor.md").write_text("TEST-ONLY via-junction", encoding="utf-8")

    workspace_root(data_dir).mkdir(parents=True, exist_ok=True)
    planted = task_workspace(data_dir, TEST_ONLY_OTHER_TASK_ID)

    if _plant_a_real_reparse_point(planted, elsewhere):
        try:
            assert planted.is_symlink() or os.path.isjunction(planted)

            with pytest.raises(WorkspaceError) as read_refusal:
                read_text(planted, "rapor.md")
            assert read_refusal.value.reason == "workspace_reparse_point"

            with pytest.raises(WorkspaceError) as list_refusal:
                list_files(planted)
            assert list_refusal.value.reason == "workspace_reparse_point"

            with pytest.raises(WorkspaceError) as write_refusal:
                write_text(planted, "yeni.md", "TEST-ONLY", replace_existing=False)
            assert write_refusal.value.reason == "workspace_reparse_point"

            with pytest.raises(WorkspaceError) as ensure_refusal:
                ensure_workspace(data_dir, TEST_ONLY_OTHER_TASK_ID)
            assert ensure_refusal.value.reason == "workspace_reparse_point"

            # Nothing on the other side was touched, and nothing came back.
            assert [item.name for item in list_files(elsewhere)] == ["rapor.md"]
        finally:
            planted.rmdir()
    else:  # pragma: no cover - only on a machine that can plant neither
        # No skip. The predicate is forced on the directory itself, which is
        # the component the real reparse point would have occupied.
        planted.mkdir(parents=True, exist_ok=True)
        (planted / "rapor.md").write_text("TEST-ONLY", encoding="utf-8")
        monkeypatch.setattr(
            os.path, "isjunction", lambda path: Path(path) == planted
        )
        with pytest.raises(WorkspaceError) as forced:
            read_text(planted, "rapor.md")
        assert forced.value.reason == "workspace_reparse_point"


def test_a_real_reparse_point_inside_the_workspace_is_refused(
    root: Path, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The leaf case, driven by a real link rather than a forced predicate.

    ``list_files`` was already iterating unresolved entries and could see a
    link one level down; ``read_text`` could not, because it resolved first.
    Both are asserted here against the same planted point.
    """
    elsewhere = data_dir / "baska"
    elsewhere.mkdir(parents=True, exist_ok=True)
    (elsewhere / "icerik.md").write_text("TEST-ONLY disarida", encoding="utf-8")
    link = root / "baglanti"

    if _plant_a_real_reparse_point(link, elsewhere):
        try:
            with pytest.raises(WorkspaceError) as listed:
                list_files(root)
            assert listed.value.reason == "workspace_reparse_point"

            with pytest.raises(WorkspaceError) as read_refusal:
                read_text(root, "baglanti")
            assert read_refusal.value.reason == "workspace_reparse_point"
        finally:
            link.rmdir()
    else:  # pragma: no cover - only on a machine that can plant neither
        monkeypatch.setattr(os.path, "isjunction", lambda _path: True)
        with pytest.raises(WorkspaceError) as forced:
            list_files(root)
        assert forced.value.reason == "workspace_reparse_point"


def test_a_listing_refuses_to_walk_a_link(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A listing that followed a link would report files from somewhere else."""
    write_text(root, "rapor.md", "TEST-ONLY", replace_existing=False)
    monkeypatch.setattr(os.path, "isjunction", lambda _path: True)

    with pytest.raises(WorkspaceError):
        list_files(root)


# ---------------------------------------------------------------------------
# Layer 4: ceilings
# ---------------------------------------------------------------------------


def test_a_file_over_the_per_file_ceiling_is_refused(root: Path) -> None:
    with pytest.raises(WorkspaceError) as caught:
        write_text(root, "big.txt", "x" * (MAX_FILE_BYTES + 1), replace_existing=False)

    assert caught.value.reason == "workspace_file_too_large"
    assert list_files(root) == ()


def test_the_file_count_ceiling_is_enforced(root: Path) -> None:
    for index in range(MAX_FILES):
        write_text(root, f"f{index}.txt", "TEST-ONLY", replace_existing=False)

    with pytest.raises(WorkspaceError) as caught:
        write_text(root, "one-too-many.txt", "TEST-ONLY", replace_existing=False)

    assert caught.value.reason == "workspace_file_count_exhausted"
    assert len(list_files(root)) == MAX_FILES


def test_the_total_byte_ceiling_is_read_from_disk_not_from_a_counter(
    root: Path,
) -> None:
    """Checked against the directory as it is, immediately before the write.

    A counter the runner keeps and a directory on disk can disagree - after a
    crash, after a manual delete, after a restart - and only one of them is
    what the user actually has.
    """
    chunk = "x" * MAX_FILE_BYTES
    written = 0
    while written + MAX_FILE_BYTES <= MAX_TOTAL_BYTES:
        write_text(root, f"c{written}.txt", chunk, replace_existing=False)
        written += MAX_FILE_BYTES

    assert total_bytes(root) == written

    with pytest.raises(WorkspaceError) as caught:
        write_text(root, "over.txt", chunk, replace_existing=False)

    assert caught.value.reason == "workspace_total_bytes_exhausted"


def test_replacing_a_file_does_not_double_count_its_bytes(root: Path) -> None:
    write_text(root, "rapor.md", "x" * 1000, replace_existing=False)
    updated = write_text(root, "rapor.md", "y" * 1000, replace_existing=True)

    assert updated.byte_count == 1000
    assert total_bytes(root) == 1000


# ---------------------------------------------------------------------------
# Create and overwrite are two intentions
# ---------------------------------------------------------------------------


def test_creating_over_an_existing_file_is_refused(root: Path) -> None:
    write_text(root, "rapor.md", "TEST-ONLY", replace_existing=False)

    with pytest.raises(WorkspaceError) as caught:
        write_text(root, "rapor.md", "TEST-ONLY-2", replace_existing=False)

    assert caught.value.reason == "workspace_file_exists"


def test_updating_a_file_that_does_not_exist_is_refused(root: Path) -> None:
    with pytest.raises(WorkspaceError) as caught:
        write_text(root, "yok.md", "TEST-ONLY", replace_existing=True)

    assert caught.value.reason == "workspace_file_missing"


def test_a_written_file_is_reported_with_its_digest(root: Path) -> None:
    produced = write_text(root, "rapor.md", "TEST-ONLY", replace_existing=False)

    assert produced.name == "rapor.md"
    assert produced.byte_count == len(b"TEST-ONLY")
    assert digest_of(root, "rapor.md") == produced.sha256


def test_a_non_utf8_file_is_refused_rather_than_guessed(root: Path) -> None:
    (root / "binary.txt").write_bytes(b"\xff\xfe\x00\x01")

    with pytest.raises(WorkspaceError) as caught:
        read_text(root, "binary.txt")

    assert caught.value.reason == "workspace_not_text"


# ---------------------------------------------------------------------------
# The directory ACL
# ---------------------------------------------------------------------------


def test_the_workspace_directory_is_restricted_to_this_user(root: Path) -> None:
    """SI-265's shape. Defence in depth rather than a trust boundary.

    A report is meant to be read, so these files are not secrets - and the
    ACL is applied anyway, and written as completeness rather than described
    as a boundary it is not.
    """
    if not is_windows():  # pragma: no cover - the suite runs on Windows
        pytest.fail("this product is Windows-only; the ACL must be checkable")

    grantees = set(acl_grantee_sids(root))

    assert current_user_sid() in grantees
    assert "S-1-5-18" in grantees, grantees
    assert grantees <= {current_user_sid(), "S-1-5-18"}, grantees


def test_a_written_file_is_restricted_too(root: Path) -> None:
    write_text(root, "rapor.md", "TEST-ONLY", replace_existing=False)

    if not is_windows():  # pragma: no cover - the suite runs on Windows
        pytest.fail("this product is Windows-only; the ACL must be checkable")

    grantees = set(acl_grantee_sids(root / "rapor.md"))

    assert grantees <= {current_user_sid(), "S-1-5-18"}, grantees


def test_the_module_has_no_archive_or_link_creating_helper() -> None:
    """The absence, asserted where a reader of this file would look for it.

    ``test_agent_boundary.py`` scans the imports; this states the same thing
    about the module's own surface, so somebody reading the workspace tests
    does not have to go looking for the reason there is no ``unpack``.
    """
    exported = set(workspace_module.__all__)

    for absent in ("unpack", "extract", "symlink", "link", "archive", "zip"):
        assert not any(absent in name.lower() for name in exported), absent
