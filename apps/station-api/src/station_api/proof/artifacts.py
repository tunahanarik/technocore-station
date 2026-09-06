"""The artifact bodies themselves, carried into the bundle rather than described.

What was measured, and why this module exists
----------------------------------------------
Until this module the bundle's artifact entries carried a name, a byte count
and a SHA-256, and nothing else. Rendering a bundle for a task whose single
artifact contained a marker string measured::

    {"json":     {"contains_filename": true,  "contains_artifact_body": false},
     "markdown": {"contains_filename": false, "contains_artifact_body": false}}

So what a person downloaded was an **inventory** of their work plus the
digests to check it against, and not the work. The report the user actually
asked for - the note, the plan, the JSON the run produced - stayed on disk and
was described. This module carries it.

(The Markdown row is not a second defect: ``escape_markdown`` renders
``rapor.json`` as ``rapor\\.json``, so a substring search for the raw name
misses. The digests were present in both formats all along.)

Verbatim, because the hash contract requires it
------------------------------------------------
Every other piece of imported text in this package goes through
:func:`~station_api.proof.bundle.safe_text` - swept, neutralised, truncated at
five hundred characters. A **body** may not: the whole point of the entry is
that ``sha256(content.encode("utf-8"))`` equals the digest recorded beside it,
and a swept, masked, truncated body is a different file. Three consequences,
all deliberate:

* the body is embedded exactly as it is on disk, and the digest is
  **re-derived from the bytes actually embedded** and compared against the
  listing's before the entry is called embedded. A file that changed between
  the listing and the read is excluded rather than shipped under a digest it
  no longer matches;
* the language registry still runs over every body, but as a **report**, not
  as a rewrite and not as a refusal: a body is data (Package E's claim/data
  split), and data may not refuse a person their own proof, nor be quietly
  edited underneath a digest. The phrases found are named in
  ``content_claim_phrases`` so a reader is told the file uses wording this
  product would not write;
* the secret scan *is* a refusal. It runs over every body before the body
  joins the document, and a hit excludes that body and names the rule. The
  bundle is the one document in this product built to be handed to somebody
  else, so it is the most likely leak surface there is, and
  ``evidence/secret_scan.py``'s own rule applies unchanged: refuse, never
  redact, never echo the value.

Where the body is delivered, and where it deliberately is not
--------------------------------------------------------------
The same review asked whether the runner's ``read_workspace_file`` tool hands
a body to the user. Measured: it does not. A run that writes ``rapor.json``
and then reads it back records ``'rapor.json' okundu: 52 karakter, ozet
172f6cc91434.`` - a summary and a digest, never the text.

That is left alone, and not only because the tool lives in another package. A
step's ``detail`` is a **row**: it is written to the database, shown in the
timeline and kept for as long as the run is. Putting up to half a megabyte of
file into it would make a second copy of every artifact, with its own
retention and its own place to leak from, in order to answer a question the
timeline is not being asked - a reader of an activity row wants to know that a
file was read, not to read it. The body belongs on a **delivery** surface, and
that is what this module and ``POST /api/proof/{task_id}/artifact`` are: the
bundle carries it under a digest, or the file is handed over as itself.

Text only, and that is a measurement rather than a limitation
--------------------------------------------------------------
There is no binary artifact to embed. The only writer into a workspace is
:func:`station_api.agent.workspace.write_text`, whose ``body`` is a ``str``
encoded UTF-8; the tool registry exposes no binary write, and
:func:`~station_api.agent.workspace.read_text` refuses anything that is not
UTF-8. So base64 would be a second encoding for a case this product cannot
produce - and a decoder is a parser, and a parser is a surface. A file that is
nevertheless not UTF-8 (dropped into the directory by hand) is **named,
excluded and explained**, which is the same answer the workspace already gives
its own reader.

Ceilings, and why one file may not lock a person out of the rest
-----------------------------------------------------------------
The package ceilings are the workspace's own three, referenced rather than
restated: 64 files, 512 KiB per file, 4 MiB in total. Referencing them is what
makes them meaningful - a workspace this product wrote cannot exceed them, so
a bundle that stays inside them embeds everything a run of this product can
produce, and the ceilings only bite on files that arrived some other way.

A body that crosses one is **excluded with the ceiling named**, in the entry
and again in the document's ``missing`` list, and never truncated: half a file
under a digest that describes the whole one is exactly the silent lie this
package exists to refuse. The refusal is per entry rather than for the whole
bundle on purpose. Refusing the bundle would let one oversized or unreadable
file - possibly one this product did not write - lock a person out of the
proof of everything else they did, which is the failure mode
``evidence/language.py`` records at length and the reason imported text may
never refuse a document here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from station_api.agent.errors import WorkspaceError
from station_api.agent.workspace import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    WorkspaceFile,
    read_text,
    task_workspace,
)
from station_api.evidence.secret_scan import scan_text
from station_api.proof.language import find_forbidden_phrases

#: The encoding a body is embedded in. One value: see the module docstring.
CONTENT_ENCODING = "utf-8"

#: An entry whose body is in the document, byte for byte.
BODY_EMBEDDED = "embedded"

#: An entry whose body is **not** in the document, with a reason that is.
BODY_EXCLUDED = "excluded"

#: Most bodies one bundle embeds. The workspace's own file ceiling.
MAX_EMBEDDED_FILES = MAX_FILES

#: Largest single body embedded. The workspace's own per-file ceiling, so a
#: file this product wrote is always inside it.
MAX_EMBEDDED_FILE_BYTES = MAX_FILE_BYTES

#: Largest total across one bundle. The workspace's own total ceiling.
MAX_EMBEDDED_TOTAL_BYTES = MAX_TOTAL_BYTES

#: Why a body is not in the document. Every value is reported to the reader.
REASON_NOT_TEXT = "not_text"
REASON_FILE_TOO_LARGE = "file_too_large"
REASON_TOTAL_EXHAUSTED = "total_bytes_exhausted"
REASON_COUNT_EXHAUSTED = "file_count_exhausted"
# ``S105`` reads the *name* and sees "secret". This is the name of a refusal
# reason, and the value is the word that appears in the document beside the
# file whose body was left out; there is no credential here and never could be
# - the whole point of the reason is that a value which looked like one was
# refused. Suppressed the way ``vault/service.py`` suppresses it for
# ``DPAPI_PASSPHRASE``, rather than renaming the reason a reader sees.
REASON_SECRET_PATTERN = "secret_pattern"  # noqa: S105
REASON_DIGEST_MISMATCH = "digest_mismatch"
REASON_NAME_REFUSED = "name_refused"
REASON_UNREADABLE = "unreadable"

#: One sentence per reason. These are sentences **this product writes**, so
#: they are checked by :func:`~station_api.proof.bundle.assert_product_language`
#: like every other one. None of them echoes a file's contents, and the
#: secret-pattern sentence in particular names only the rule - a refusal that
#: printed the value would be the leak it had just prevented.
EXCLUSION_DETAIL: dict[str, str] = {
    REASON_NOT_TEXT: (
        "Dosyanin govdesi pakete alinmadi: icerik UTF-8 metin degil. Bu "
        "surumde yalnizca metin govdesi tasinir; adi, bayt sayisi ve SHA-256 "
        "ozeti listede kalir."
    ),
    REASON_FILE_TOO_LARGE: (
        f"Dosyanin govdesi pakete alinmadi: {MAX_EMBEDDED_FILE_BYTES} baytlik "
        "tekil dosya tavani asildi. Govde kirpilmaz - eksik bir govde, tam "
        "dosyayi tanimlayan bir ozetin altinda durur ve bu yanlis olurdu."
    ),
    REASON_TOTAL_EXHAUSTED: (
        f"Dosyanin govdesi pakete alinmadi: paketin "
        f"{MAX_EMBEDDED_TOTAL_BYTES} baytlik toplam govde tavani bu dosyayla "
        "asilirdi. Diger dosyalar etkilenmez ve bu dosya adiyla listelenmeye "
        "devam eder."
    ),
    REASON_COUNT_EXHAUSTED: (
        f"Dosyanin govdesi pakete alinmadi: paketin {MAX_EMBEDDED_FILES} "
        "dosyalik govde tavanina ulasildi. Dosya adiyla, bayt sayisiyla ve "
        "ozetiyle listelenmeye devam eder."
    ),
    REASON_SECRET_PATTERN: (
        "Dosyanin govdesi pakete alinmadi: gizli deger taramasi bir kural "
        "eslesmesi buldu. Paket kullaniciya teslim edilen belgedir, bu yuzden "
        "govde redakte edilmez, disarida birakilir; eslesen deger hicbir yere "
        "yazilmaz."
    ),
    REASON_DIGEST_MISMATCH: (
        "Dosyanin govdesi pakete alinmadi: okunan baytlarin ozeti, listelenen "
        "ozetle ayni degil. Dosya listeleme ile okuma arasinda degismis "
        "olabilir; eslesmeyen bir govde ozetin altinda tasinmaz."
    ),
    REASON_NAME_REFUSED: (
        "Dosyanin govdesi pakete alinmadi: dosya adi calisma alaninin izin "
        "verdigi karakter kumesinin disinda. Bu dosyayi bu surum yazmadi."
    ),
    REASON_UNREADABLE: (
        "Dosyanin govdesi pakete alinmadi: dosya okunamadi. Adi, bayt sayisi "
        "ve ozeti listede kalir."
    ),
}

#: Which workspace refusals become a per-entry exclusion, and which do not.
#:
#: Deliberately short. ``workspace_reparse_point`` and ``workspace_escape`` are
#: **absent**: a link or an escape inside a task workspace is a statement about
#: the machine rather than about one file, and the whole read already refuses
#: on it - ``AgentService.workspace_files`` raises before this module runs, and
#: ``routes/proof.py`` turns that into a stated refusal. Mapping either to a
#: quiet per-file note here would take a defence that currently stops a proof
#: read and reduce it to a line in a table.
_EXCLUDABLE_WORKSPACE_REASONS: dict[str, str] = {
    "workspace_not_text": REASON_NOT_TEXT,
    "workspace_file_too_large": REASON_FILE_TOO_LARGE,
    "workspace_file_missing": REASON_UNREADABLE,
    "workspace_name_refused": REASON_NAME_REFUSED,
}

#: Every sentence this module authors, for the product-language guard.
EXCLUSION_SENTENCES: tuple[str, ...] = tuple(EXCLUSION_DETAIL.values())


@dataclass(frozen=True, slots=True)
class ArtifactBody:
    """One workspace file, with its body when the body could be carried.

    ``sha256`` is always the digest of the **file**, whether or not the body is
    embedded, so an excluded entry is still checkable against a copy the reader
    holds. When ``state`` is :data:`BODY_EMBEDDED`, ``content`` is the exact
    text whose UTF-8 encoding hashes to that value.
    """

    name: str
    byte_count: int
    sha256: str
    state: str
    content: str | None
    detail: str
    #: Phrases from the language registry found **inside the file**. Reported,
    #: never removed: removing them would change the bytes the digest covers.
    claim_phrases: tuple[str, ...]

    @property
    def embedded(self) -> bool:
        return self.state == BODY_EMBEDDED


def _excluded(item: WorkspaceFile, reason: str, *, detail: str = "") -> ArtifactBody:
    return ArtifactBody(
        name=item.name,
        byte_count=item.byte_count,
        sha256=item.sha256,
        state=BODY_EXCLUDED,
        content=None,
        detail=detail or EXCLUSION_DETAIL[reason],
        claim_phrases=(),
    )


def _ceiling_crossed(
    item: WorkspaceFile, *, index: int, embedded_bytes: int
) -> str | None:
    """The ceiling this file crosses, if it crosses one. Checked before reading.

    Order matters only in that the cheapest refusals come first: a file over a
    ceiling is never opened, so a workspace somebody filled by hand cannot make
    a proof read do the work of reading it.

    The per-file line is **redundant by construction and kept anyway**, and
    that was measured rather than assumed: deleting it changes no observable
    outcome, because :func:`~station_api.agent.workspace.read_text` enforces
    the same ceiling and its refusal is mapped straight back to the same
    reason. Deleting *both* does change the outcome - the read stops being a
    per-file exclusion and refuses the whole bundle - and a test catches that.
    What the line still buys is that half a megabyte is not read into memory in
    order to be told it is half a megabyte.
    """
    if index >= MAX_EMBEDDED_FILES:
        return REASON_COUNT_EXHAUSTED
    if item.byte_count > MAX_EMBEDDED_FILE_BYTES:
        return REASON_FILE_TOO_LARGE
    if embedded_bytes + item.byte_count > MAX_EMBEDDED_TOTAL_BYTES:
        return REASON_TOTAL_EXHAUSTED
    return None


def read_bodies(
    directory: Path, files: Sequence[WorkspaceFile]
) -> tuple[ArtifactBody, ...]:
    """Read every listed file's body through the workspace's own defences.

    :func:`station_api.agent.workspace.read_text` is called rather than a path
    being opened here, and that is the load-bearing sentence of this module:
    the reparse-point walk over the unresolved path, the allow-list rebuild of
    the name, the containment check and the per-file ceiling all run on every
    body. The proof package gains no second way into a workspace - it goes
    through the one that already exists.
    """
    bodies: list[ArtifactBody] = []
    embedded_bytes = 0

    for index, item in enumerate(files):
        crossed = _ceiling_crossed(item, index=index, embedded_bytes=embedded_bytes)
        if crossed is not None:
            bodies.append(_excluded(item, crossed))
            continue

        try:
            body = read_text(directory, item.name)
        except WorkspaceError as exc:
            mapped = _EXCLUDABLE_WORKSPACE_REASONS.get(exc.reason)
            if mapped is None:
                raise
            bodies.append(_excluded(item, mapped))
            continue
        except OSError:  # pragma: no cover - filesystem dependent
            bodies.append(_excluded(item, REASON_UNREADABLE))
            continue

        payload = body.encode(CONTENT_ENCODING)
        if hashlib.sha256(payload).hexdigest() != item.sha256:
            bodies.append(_excluded(item, REASON_DIGEST_MISMATCH))
            continue

        finding = scan_text(body, where=f"artifact:{item.name}")
        if finding is not None:
            bodies.append(
                _excluded(
                    item,
                    REASON_SECRET_PATTERN,
                    detail=(
                        f"{EXCLUSION_DETAIL[REASON_SECRET_PATTERN]} Kural: "
                        f"{finding.rule.value}."
                    ),
                )
            )
            continue

        bodies.append(
            ArtifactBody(
                name=item.name,
                byte_count=len(payload),
                sha256=item.sha256,
                state=BODY_EMBEDDED,
                content=body,
                detail="",
                claim_phrases=find_forbidden_phrases(body),
            )
        )
        embedded_bytes += len(payload)

    return tuple(bodies)


def read_workspace_bodies(
    data_dir: Path, task_id: str, files: Sequence[WorkspaceFile]
) -> tuple[ArtifactBody, ...]:
    """The bodies for one task, addressed by its application-generated id."""
    return read_bodies(task_workspace(data_dir, task_id), files)


def listed_only(files: Sequence[WorkspaceFile]) -> tuple[ArtifactBody, ...]:
    """Every file listed with no body at all, each one saying so.

    The shape a bundle takes where the workspace root is not known to this
    process. It exists so that "no bodies" is a **stated** condition with a
    reason a reader sees, rather than a silently thinner document that looks
    exactly like a task whose files happened to be unreadable.
    """
    return tuple(_excluded(item, REASON_UNREADABLE) for item in files)


__all__ = [
    "BODY_EMBEDDED",
    "BODY_EXCLUDED",
    "CONTENT_ENCODING",
    "EXCLUSION_DETAIL",
    "EXCLUSION_SENTENCES",
    "MAX_EMBEDDED_FILES",
    "MAX_EMBEDDED_FILE_BYTES",
    "MAX_EMBEDDED_TOTAL_BYTES",
    "REASON_COUNT_EXHAUSTED",
    "REASON_DIGEST_MISMATCH",
    "REASON_FILE_TOO_LARGE",
    "REASON_NAME_REFUSED",
    "REASON_NOT_TEXT",
    "REASON_SECRET_PATTERN",
    "REASON_TOTAL_EXHAUSTED",
    "REASON_UNREADABLE",
    "ArtifactBody",
    "listed_only",
    "read_bodies",
    "read_workspace_bodies",
]
