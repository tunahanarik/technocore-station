"""The one path from what a run produced to what a person may sign.

Why this module exists
----------------------
A scan found real work in a public room, a run produced the text for it, and
there was no way to act on it. The tool registry has no send tool and gains
none (ADR-0016); the composer could not see a workspace file. The only route
from one half to the other was a person retyping the bytes, which is friction
*and* a place for the bytes to change between what was produced and what gets
signed.

This module is that route, and it is a **read**. It offers a task's workspace
files as candidates, and hands back the exact bytes of the one a person picks.
It signs nothing, reserves nothing, sends nothing and decides nothing about a
destination.

What it deliberately does not carry
------------------------------------
**A room.** Not in the candidate, not in the body, not anywhere in this
module - there is no field of any name that could hold one, and a test reads
the dataclasses to say so. The text a run drafted is derived from lines a
stranger wrote in a public room (``workscan/authority.py``, level 3
``community``), and ``test_work_scan_model_reading.py`` already plants a line
claiming the user pre-approved everything there. A body that says "post this
to /r/somewhere" is a stranger choosing a destination; letting that string
reach the target field - even as a suggestion, even greyed out, even as a
placeholder - would make the most consequential field on the surface the one
piece of it an outsider writes.

So the room is typed by the person, every time. They can read the mention in
the body, which is displayed verbatim; what they cannot do is have it filled
in for them.

**A second way into a workspace.** Bodies are read through
:func:`station_api.proof.artifacts.read_bodies`, which reads through
:func:`station_api.agent.workspace.read_text` - the allow-list name rebuild,
the reparse-point walk on the unresolved path, the containment check and the
three ceilings all apply unchanged, and the secret-shape scan and the
digest re-check that the proof package added apply too. This module opens no
path and holds no root of its own; it is handed one.

That reuse is the point rather than a convenience. The proof bundle and the
composer are the two surfaces in this product that take bytes out of a
workspace and put them in front of a person, and two readers with the same job
is exactly the duplication ADR-0004 2 named - the expensive kind, because the
cheaper copy is the one that would quietly miss a defence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from station_api.agent.errors import WorkspaceError
from station_api.agent.workspace import WorkspaceFile
from station_api.proof.artifacts import ArtifactBody, read_workspace_bodies

#: Most tasks one listing walks. A ceiling rather than a page: the surface is
#: "which of my runs produced something I might send", and a person does not
#: read past a few dozen. Newest first, so the ceiling drops the stale end.
MAX_LISTED_TASKS = 40


class TaskDraftError(Exception):
    """A draft could not be offered or read. The message is safe to show."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class WorkspaceSource(Protocol):
    """The one thing this module asks the agent runtime for.

    One method, for :class:`~station_api.compose.service.ComposeIdentity`'s
    reason: the composer has no business with runs, plans, budgets or the
    activity timeline, and a dependency that named ``AgentService`` would be
    one that could grow into them. ``AgentService`` satisfies this
    structurally.
    """

    def workspace_files(self, task_id: str) -> tuple[WorkspaceFile, ...]:
        """What one task's workspace holds. A read; creates nothing."""
        ...  # pragma: no cover - protocol declaration


class TaskSource(Protocol):
    """The one thing this module asks the task layer for."""

    def list_tasks(self) -> tuple[object, ...]:
        """Every task, newest first."""
        ...  # pragma: no cover - protocol declaration


@dataclass(frozen=True, slots=True)
class TaskDraftCandidate:
    """One workspace file a person could load into the composer.

    There is no ``room``, no ``target``, no ``url`` and no ``recipient`` here,
    and there must never be: see this module's docstring. What a candidate
    carries is an identity (which task, which file), a size, a digest and -
    when the body cannot be offered - the reason, in the proof package's own
    words.
    """

    task_id: str
    task_title: str
    name: str
    byte_count: int
    sha256: str
    #: False when the body cannot be handed over: not UTF-8, over a ceiling,
    #: refused by the secret-shape scan, or changed since it was listed.
    loadable: bool
    #: Why not, when ``loadable`` is False. Empty otherwise.
    detail: str


@dataclass(frozen=True, slots=True)
class TaskDraftBody:
    """The exact bytes of one produced file, on their way to step 1.

    ``text`` is verbatim: not swept, not truncated, not summarised. The sweep
    belongs to :meth:`~station_api.compose.service.ComposeService.draft`,
    which shows the person what it changed before anything is signed, and a
    body pre-swept here would make that comparison a comparison against
    itself. ``sha256`` is the digest of the file on disk, so the surface can
    say that what it is showing is what the run wrote.
    """

    task_id: str
    task_title: str
    name: str
    byte_count: int
    sha256: str
    text: str
    #: Phrases the language registry found **in the file**. Reported, never
    #: removed - the proof package's rule, for the proof package's reason: a
    #: body is data, and editing data underneath a digest is a lie.
    claim_phrases: tuple[str, ...]


class TaskDraftReader:
    """Reads produced drafts out of task workspaces. Writes nothing, ever."""

    def __init__(
        self, *, data_dir: Path, workspace: WorkspaceSource, tasks: TaskSource
    ) -> None:
        self._data_dir = data_dir
        self._workspace = workspace
        self._tasks = tasks

    def candidates(self) -> tuple[TaskDraftCandidate, ...]:
        """Every loadable file every task produced, newest task first.

        A workspace that refuses to be listed at all - a reparse point on the
        task directory, an escape - is **skipped rather than raised over**.
        One broken task must not take the whole surface down with it, which is
        the per-entry rule ``proof/artifacts.py`` settled for the same reason;
        the proof read still refuses loudly for that task, so the condition is
        reported where it is actionable rather than swallowed everywhere.
        """
        found: list[TaskDraftCandidate] = []
        for task in self._tasks.list_tasks()[:MAX_LISTED_TASKS]:
            task_id = str(getattr(task, "id", ""))
            title = str(getattr(task, "title", ""))
            if not task_id:  # pragma: no cover - TaskView always carries one
                continue
            try:
                files = self._workspace.workspace_files(task_id)
            except WorkspaceError:
                continue
            if not files:
                continue
            found.extend(self._describe(task_id, title, files))
        return tuple(found)

    def _describe(
        self, task_id: str, title: str, files: tuple[WorkspaceFile, ...]
    ) -> list[TaskDraftCandidate]:
        """Turn one task's files into candidates, reading each body once.

        The bodies are read rather than only listed, because "loadable" is a
        claim about the bytes: a file that is not UTF-8, crosses a ceiling or
        trips the secret-shape scan cannot be handed over, and saying so on
        the listing is what keeps a person from picking one that will refuse.
        """
        bodies = self._read_bodies(task_id, files)
        return [
            TaskDraftCandidate(
                task_id=task_id,
                task_title=title,
                name=body.name,
                byte_count=body.byte_count,
                sha256=body.sha256,
                loadable=body.embedded,
                detail="" if body.embedded else body.detail,
            )
            for body in bodies
        ]

    def body(self, task_id: str, name: str) -> TaskDraftBody:
        """The exact bytes of one produced file, or a refusal that says why."""
        try:
            files = self._workspace.workspace_files(task_id)
        except WorkspaceError as exc:
            raise TaskDraftError(str(exc), reason=exc.reason) from exc

        wanted = [item for item in files if item.name == name]
        if not wanted:
            raise TaskDraftError(
                "Bu gorevin calisma alaninda bu adda bir dosya yok. Liste "
                "yenilendiginde dosya silinmis olabilir.",
                reason="task_draft_missing",
            )

        body = self._read_bodies(task_id, tuple(wanted))[0]
        if not body.embedded:
            raise TaskDraftError(body.detail, reason="task_draft_unreadable")

        # ``read_bodies`` only sets ``content`` on an embedded entry, and the
        # branch above returned for every other state. The guard is here
        # because the type is ``str | None`` and a ``None`` reaching the
        # composer would become an empty message rather than a refusal.
        if body.content is None:  # pragma: no cover - embedded implies content
            raise TaskDraftError(
                "Dosyanin govdesi okunamadi.", reason="task_draft_unreadable"
            )

        return TaskDraftBody(
            task_id=task_id,
            task_title=self._title_of(task_id),
            name=body.name,
            byte_count=body.byte_count,
            sha256=body.sha256,
            text=body.content,
            claim_phrases=body.claim_phrases,
        )

    def _read_bodies(
        self, task_id: str, files: tuple[WorkspaceFile, ...]
    ) -> tuple[ArtifactBody, ...]:
        try:
            return read_workspace_bodies(self._data_dir, task_id, files)
        except WorkspaceError as exc:
            raise TaskDraftError(str(exc), reason=exc.reason) from exc

    def _title_of(self, task_id: str) -> str:
        for task in self._tasks.list_tasks():
            if str(getattr(task, "id", "")) == task_id:
                return str(getattr(task, "title", ""))
        return ""  # pragma: no cover - the workspace read already found it


__all__ = [
    "MAX_LISTED_TASKS",
    "TaskDraftBody",
    "TaskDraftCandidate",
    "TaskDraftError",
    "TaskDraftReader",
    "TaskSource",
    "WorkspaceSource",
]
