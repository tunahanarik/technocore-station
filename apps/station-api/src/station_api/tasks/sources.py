"""Where a task came from, and the identity that makes evidence non-reusable.

ADR-0004 5. A task is bound to a **source version**::

    source_version_id = domain_digest(
        b"technocore-station/task-source/v1", source_id, content_sha256
    )

Two properties follow, and both are the point:

* the source identifier comes from the closed enum below, never from a
  caller-supplied string. Same reason ``OfficialSourceSnapshot.source_id``
  does: an identity built from free text is an identity an attacker chooses;
* changing the content changes the identity, so **evidence produced for the
  old content stops matching**. This is ``verdict_id``'s fail-closed reading
  applied to task content: any new check produces a new identity even when it
  finds the same thing, because the user approved against the evidence they
  saw, not against the conclusion it happened to reach.

The digest is domain-separated and length-prefixed
(:mod:`station_api.digests`), so an identity built for a task source can never
be presented as one built for anything else, and two fields cannot impersonate
a differently-split pair.
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum

from station_api.digests import domain_digest

#: Domain separation for the task-source binding. Versioned: a change to what
#: goes into the identity gets a new domain rather than silently reusing this
#: one, so an old identity can never be read as a new-format one.
TASK_SOURCE_DOMAIN = b"technocore-station/task-source/v1"

#: Lowercase hex, exactly 32 bytes' worth. Compared literally so an uppercase
#: or truncated digest is a refusal rather than a second spelling of the same
#: identity.
_SHA256_HEX = re.compile(r"\A[0-9a-f]{64}\Z")


class TaskSourceId(StrEnum):
    """The closed set of things a task may be derived from."""

    #: The user described the work themselves.
    OPERATOR_REQUEST = "operator_request"
    #: Derived from a record in the compile-time module registry.
    PROJECT_MODULE = "project_module"
    #: Derived from an archived send in the evidence ledger.
    EVIDENCE_ARCHIVE = "evidence_archive"


#: Why each source exists, in one Turkish sentence.
SOURCE_DETAIL: dict[TaskSourceId, str] = {
    TaskSourceId.OPERATOR_REQUEST: (
        "Kullanicinin kendi tarif ettigi is. Icerik veri olarak islenir; "
        "talimat olarak degil."
    ),
    TaskSourceId.PROJECT_MODULE: (
        "Derleme zamani modul registry'sindeki bir kayittan turetildi."
    ),
    TaskSourceId.EVIDENCE_ARCHIVE: (
        "Kanit defterindeki arsivlenmis bir gonderimden turetildi."
    ),
}


class TaskSourceError(Exception):
    """A task source or content version was rejected. Safe to show."""


def content_sha256(payload: bytes) -> str:
    """SHA-256 over the exact content bytes, lowercase hex."""
    return hashlib.sha256(payload).hexdigest()


def source_version_id(source: TaskSourceId, content_hash: str) -> str:
    """The identity a task and its evidence are both bound to.

    ``source`` must be a registry member. The runtime check is not redundant
    with the type annotation: ``TaskSourceId`` is a ``StrEnum``, so a plain
    string satisfies every ``isinstance(value, str)`` test the rest of the
    codebase performs, and only an explicit enum check keeps a free string
    from becoming an identity.
    """
    if not isinstance(source, TaskSourceId):
        raise TaskSourceError(
            "Gorev kaynagi registry'den gelmelidir; serbest metin kabul edilmez."
        )
    if not _SHA256_HEX.match(content_hash):
        raise TaskSourceError(
            "Icerik ozeti 64 karakterlik kucuk harfli hex olmalidir."
        )
    return domain_digest(TASK_SOURCE_DOMAIN, source.value, content_hash)


__all__ = [
    "SOURCE_DETAIL",
    "TASK_SOURCE_DOMAIN",
    "TaskSourceError",
    "TaskSourceId",
    "content_sha256",
    "source_version_id",
]
