"""The proof bundle: one deterministic document, in two formats, written nowhere.

Where this shape comes from
---------------------------
``evidence/export.py``, exactly (ADR-0009 3). The dominant pattern in this
repository is written down in ``downloads.py``: *Station hands the file to the
browser instead of writing it to a path the user chose, and that decision
removes path traversal, symlinks, reparse points and overwrite questions from
the product entirely.* A proof bundle is a file a person wants a copy of, so
it is delivered the same way and **no new file root is opened**.

It is emphatically not written into ``workspace/v1/<task_id>``. The artifact
set digest below covers every file in that directory, so a bundle placed there
would be an input to its own hash.

**No archive is produced.** Zip-slip is a bug class that arises from
*unpacking*, not from packing - that distinction is recorded here rather than
waved at - but a zip buys no behaviour, and
``test_the_module_has_no_archive_or_link_creating_helper`` is a test that reads
names. Producing none means the surface never exists.

Determinism, unconditionally
-----------------------------
The same task, artifacts and runs produce the same bytes on every call. JSON
goes through :func:`~station_api.strict_json.canonical_json_bytes`; the
Markdown writer emits fixed sections in a fixed order with ``\\n`` endings.
There is no "prepared at" anywhere in either document: when a copy was made is
a fact about the copy, not about the proof, and stamping it inside would give
"prepare twice and diff" a footnote nobody reading the file would know about.
The moment travels in a response header instead, as it does for the evidence
export.

That determinism is load-bearing here in a way it is not there: the single-use
share approval is bound to :func:`bundle_sha256`, so an unchanged bundle has
to hash the same or every approval would expire the instant it was minted, and
a changed bundle has to hash differently or a stale approval would deliver
content nobody approved.

What the digest proves, and what it does not
---------------------------------------------
:data:`~station_api.proof.language.HASH_SCOPE_SENTENCE` is written into both
formats, and ADR-0009 11 is the reason: a digest fixes bytes. It says nothing
about whether those bytes are right or useful, and the word *proof* in a
heading must not be read as *proven*.

Imported text is neutralised, never a reason to refuse
-------------------------------------------------------
A task title, a file name and a plan's success criterion are the user's own
words. They are swept, neutralised and escaped where they are rendered
(Package E's claim/data split); the fixed sentences this product authors are
the ones checked, and a forbidden phrase in one of those fails closed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from station_api.agent.service import (
    TEST_RESULT_DETAIL,
    TEST_RESULT_STATE,
    RunView,
)
from station_api.agent.workspace import WorkspaceFile
from station_api.digests import domain_digest_bytes
from station_api.evidence.export import escape_markdown
from station_api.modules.completion import ModuleCompletion
from station_api.modules.fields import FIELD_DETAIL
from station_api.proof.language import (
    BUNDLE_SCOPE_SENTENCE,
    HASH_SCOPE_SENTENCE,
    assert_no_forbidden_claim,
    neutralise,
)
from station_api.strict_json import canonical_json_bytes
from station_api.tasks.gate import TaskGateStatus
from station_api.tasks.service import TaskView
from station_api.technocore.projection import sweep_untrusted

#: The two formats. A closed set: a third would be a third writer to keep
#: deterministic and a third escaping problem to get right.
BundleFormat = Literal["json", "markdown"]

BUNDLE_FORMATS: tuple[BundleFormat, ...] = ("json", "markdown")

BUNDLE_SUFFIX: dict[str, str] = {"json": ".json", "markdown": ".md"}

BUNDLE_MEDIA_TYPE: dict[str, str] = {
    # ``charset`` is stated rather than left to the client: a Markdown file
    # full of Turkish read as latin-1 is a different document.
    "json": "application/json; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8",
}

#: Bumped when the document's shape changes, so an old file is never read
#: under new rules.
BUNDLE_VERSION = 1

BUNDLE_KIND = "technocore-station.proof-bundle"

#: Domain separation for the bundle digest and for the artifact set digest. A
#: digest is only meaningful against the thing it was computed for.
BUNDLE_DOMAIN = b"technocore-station/proof-bundle/v1"

#: The download name's stem. A constant; the suffix goes through the
#: sanitiser and is never interpolated raw (ADR-0003 9).
BUNDLE_STEM = "technocore-station-kanit-paketi"

#: The two fields ADR-0009 6 and 7 hold at ``not_implemented``, spelled the
#: way every other three-valued state in this product is spelled.
NOT_IMPLEMENTED = "not_implemented"

#: ADR-0009 6. The model lane is closed, so there is no second opinion to
#: record - and a run's own output presented as somebody else's verdict is the
#: dishonesty this field exists to refuse. A **closure**, not a policy refusal:
#: the same distinction ``run_test_result_recorded`` is written under.
INDEPENDENT_CHECK_DETAIL = (
    "Bagimsiz kontrol bu surumde uygulanmadi. Model yolu kapalidir, bu yuzden "
    "kaydedilecek ikinci bir gorus yoktur; ayni kosmanin kendi ciktisi disaridan "
    "gelen bir onay gibi sunulmaz. Alan bos degil, 'uygulanmadi' olarak "
    "raporlanir ve nedeni budur."
)

#: ADR-0009 7. Arbitrary execution is closed, so nothing produces an exit
#: code. The criterion and the instruction for re-deriving it are packaged as
#: text; a number is not invented to fill the space where a result would go.
EXIT_CODE_DETAIL = (
    "Gercek bir cikis kodu uretilmedi. Keyfi kod ve kabuk yurutmesi kapalidir, "
    "bu yuzden kosacak bir denetim yoktur. Planin basari olcutu ve yeniden "
    "uretme talimati asagida metin olarak yer alir; sayi uydurulmaz."
)

#: How a reader re-derives what the bundle states. Written as an instruction
#: rather than as a claim, because re-deriving it is the reader's act.
REPRODUCTION_DETAIL = (
    "Yeniden uretmek icin: her dosyanin SHA-256 degerini kendi kopyanizla "
    "karsilastirin, sonra kume ozetini ad ve ozet ciftlerinin kanonik JSON'u "
    "uzerinden alin. Ayni dosya kumesi her seferinde ayni kume ozetini verir. "
    "Planin olcutu asagidadir ve bu surumde kosulmaz."
)

#: Every sentence **this product itself writes** into a bundle, as opposed to
#: every string that ends up in one. Checked before a document is built. A
#: task title, a file name and a success criterion are deliberately absent:
#: they are data, they are neutralised and escaped, and they may not refuse a
#: file - the lesson ``evidence/language.py`` records.
PRODUCT_SENTENCES: tuple[str, ...] = (
    HASH_SCOPE_SENTENCE,
    BUNDLE_SCOPE_SENTENCE,
    INDEPENDENT_CHECK_DETAIL,
    EXIT_CODE_DETAIL,
    REPRODUCTION_DETAIL,
    TEST_RESULT_DETAIL,
)

#: Longest interpolated value kept in a bundle sentence.
MAX_BUNDLE_TEXT_CHARS = 500


class BundleFormatError(Exception):
    """A format outside the closed set was asked for."""


@dataclass(frozen=True, slots=True)
class ProofBundle:
    """One built bundle: its document and the digest an approval binds to."""

    task_id: str
    source_version_id: str
    document: dict[str, Any]
    sha256: str


def safe_text(value: str) -> str:
    """Sweep, neutralise and bound one piece of the user's own text.

    In that order, and the order is the whole of IMP-420: sweeping removes
    control and bidi characters, neutralising removes a forbidden phrase
    *before* the value joins one of our sentences, and bounding keeps a
    pasted novel out of a document meant to be read. Neutralising after the
    guard would make the guard a no-op, which is exactly how Package H2's
    first attempt went wrong.

    Sweeping before neutralising is the half that is easy to get backwards,
    and getting it backwards is not cosmetic. The two functions disagree about
    invisible characters on purpose: :func:`fold` **deletes** them, because
    ``w<ZWSP>allet`` is one word to a reader, while
    :func:`~station_api.technocore.projection.sweep_untrusted` **replaces**
    them with a space, because a marker hidden behind one must not survive
    into a scanned sentence. So a zero-width space between two words of a
    forbidden phrase makes that phrase invisible to ``neutralise`` and visible
    again after the sweep: with the calls swapped, the phrase reaches
    :func:`assert_no_forbidden_claim` intact and a note a person typed becomes
    an unhandled error on their own acceptance. Swapping them is measured, not
    assumed - ``test_proof_language.py`` drives a note carrying exactly that
    character.
    """
    return neutralise(sweep_untrusted(value)).strip()[:MAX_BUNDLE_TEXT_CHARS]


def assert_product_language(*, where: str) -> None:
    """Refuse to build a bundle if one of *our own* sentences over-claims.

    The finished document is deliberately **not** scanned: it also carries a
    task title and file names, and letting either of those refuse the bundle
    would let a keyboard lock a person out of their own proof, permanently, in
    both formats (:mod:`station_api.evidence.language`).
    """
    for sentence in PRODUCT_SENTENCES:
        assert_no_forbidden_claim(sentence, where=where)


def artifact_set_sha256(files: Sequence[WorkspaceFile]) -> str:
    """One digest over the whole produced set, so a review has one anchor.

    Byte-for-byte the computation ``AgentService`` already performs when a run
    finishes - plain SHA-256 over the canonical JSON of name/digest pairs - so
    the number a run recorded in its activity row and the number a bundle
    reports are **the same number**, not two numbers that happen to agree
    today. It is deliberately *not* domain-separated the way
    :func:`bundle_sha256` is: matching the existing value is the point, and a
    domain prefix here would produce a second, different anchor for one fact.

    It is computed in two places because the agent package cannot import this
    one - this module imports *it*, and the reverse would be a cycle - so a
    test pins the agreement rather than an import.
    """
    return hashlib.sha256(
        canonical_json_bytes(
            {"files": [{"name": item.name, "sha256": item.sha256} for item in files]}
        )
    ).hexdigest()


def bundle_sha256(document: dict[str, Any]) -> str:
    """The digest a share approval is bound to, over the canonical document."""
    return domain_digest_bytes(BUNDLE_DOMAIN, canonical_json_bytes(document))


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _artifact_entries(files: Sequence[WorkspaceFile]) -> list[dict[str, Any]]:
    return [
        {
            "name": safe_text(item.name),
            "byte_count": item.byte_count,
            "sha256": item.sha256,
        }
        for item in files
    ]


def _run_entry(view: RunView) -> dict[str, Any]:
    return {
        "id": view.id,
        "phase": view.phase.value,
        "created_at": _iso(view.created_at),
        "started_at": _iso(view.started_at),
        "finished_at": _iso(view.finished_at),
        "plan_sha256": view.plan_sha256,
        "test_condition": safe_text(view.test_condition),
        "test_result_state": view.test_result_state,
        "expected_artifacts": [safe_text(name) for name in view.expected_artifacts],
        "tool_calls_used": view.tool_calls_used,
        "max_tool_calls": view.max_tool_calls,
        "steps": [
            {
                "ordinal": step.ordinal,
                "tool_id": step.tool_id,
                "scope": step.scope,
                "phase": step.phase.value,
                "arguments_sha256": step.arguments_sha256,
                "artifact_name": safe_text(step.artifact_name),
                "artifact_sha256": step.artifact_sha256,
            }
            for step in view.steps
        ],
    }


def _missing_entries(
    *,
    gate: TaskGateStatus,
    completion: ModuleCompletion,
    runs: Sequence[RunView],
    files: Sequence[WorkspaceFile],
) -> list[dict[str, str]]:
    """Every gap, named. Absence is stated, never left to be noticed.

    The list is built from four independent sources rather than from one
    summary, because a summary is precisely what this product refuses to hand
    a reader: an evidence field that is blocked, a module requirement that
    cannot be produced, a run that did not finish and a promised artifact that
    is not on disk are four different problems with four different remedies.
    """
    entries: list[dict[str, str]] = []

    for check in gate.checks:
        if check.state.value != "passed":
            entries.append(
                {
                    "key": f"evidence.{check.field.value}",
                    "state": check.state.value,
                    "detail": safe_text(check.detail) or FIELD_DETAIL[check.field],
                }
            )

    for module_check in completion.checks:
        if module_check.state.value != "passed":
            entries.append(
                {
                    "key": f"requirement.{module_check.key}",
                    "state": module_check.state.value,
                    "detail": safe_text(module_check.detail),
                }
            )

    present = {item.name for item in files}
    for view in runs:
        if view.phase.value != "completed":
            entries.append(
                {
                    "key": f"run.{view.id}",
                    "state": view.phase.value,
                    "detail": (
                        "Bu calisma 'completed' ile bitmedi; asamasi "
                        f"'{view.phase.value}'."
                    ),
                }
            )
        for name in view.expected_artifacts:
            if name not in present:
                entries.append(
                    {
                        "key": f"artifact.{safe_text(name)}",
                        "state": "absent",
                        "detail": (
                            "Plan bu ciktiyi soz verdi ve calisma alaninda "
                            "bulunamadi."
                        ),
                    }
                )

    if not runs:
        entries.append(
            {
                "key": "run.none",
                "state": "absent",
                "detail": "Bu gorev icin kayitli bir calisma yok.",
            }
        )

    return entries


def build_document(
    *,
    task: TaskView,
    gate: TaskGateStatus,
    completion: ModuleCompletion,
    runs: Sequence[RunView],
    files: Sequence[WorkspaceFile],
) -> dict[str, Any]:
    """Assemble the bundle. Computes no verdict of its own.

    Every state in here was decided somewhere else - by
    :mod:`station_api.tasks.gate`, by
    :mod:`station_api.modules.completion`, by the runner. This function copies
    values, names gaps and writes the four fixed sentences; it has no opinion
    to add, which is what keeps a second gate out of a package that would
    otherwise be a natural place to grow one (ADR-0004 2).
    """
    assert_product_language(where="proof bundle")

    return {
        "kind": BUNDLE_KIND,
        "version": BUNDLE_VERSION,
        "task": {
            "id": task.id,
            "module_id": task.module_id,
            "source_id": task.source_id,
            "title": safe_text(task.title),
            "state": task.state.value,
            "state_detail": task.state_detail,
            "content_sha256": task.content_sha256,
            "source_version_id": task.source_version_id,
            "created_at": _iso(task.created_at),
            "updated_at": _iso(task.updated_at),
        },
        "artifacts": {
            "file_count": len(files),
            "total_bytes": sum(item.byte_count for item in files),
            "set_sha256": artifact_set_sha256(files),
            "files": _artifact_entries(files),
        },
        "evidence_fields": [
            {
                "field": check.field.value,
                "state": check.state.value,
                "ref_id": check.ref_id,
                "detail": safe_text(check.detail),
            }
            for check in gate.checks
        ],
        "ready_to_publish": gate.ready_to_publish,
        "blocking_fields": list(gate.blocking_fields),
        "module": {
            "id": completion.module_id,
            "complete": completion.complete,
            "blocking_keys": list(completion.blocking_keys),
            "not_implemented_keys": list(completion.not_implemented_keys),
        },
        "runs": [_run_entry(view) for view in runs],
        # The two fields that stay empty and say why (ADR-0009 6, 7). Written
        # as objects with a state rather than omitted, so a reader sees the
        # decision instead of a missing key - level 4's rule, applied here.
        "claims": {
            "independent_check": {
                "state": NOT_IMPLEMENTED,
                "detail": INDEPENDENT_CHECK_DETAIL,
            },
            "exit_code": {
                "state": NOT_IMPLEMENTED,
                "detail": EXIT_CODE_DETAIL,
            },
            "test_result": {
                "state": TEST_RESULT_STATE,
                "detail": TEST_RESULT_DETAIL,
            },
        },
        "missing": _missing_entries(
            gate=gate, completion=completion, runs=runs, files=files
        ),
        "notes": {
            "hash_scope": HASH_SCOPE_SENTENCE,
            "bundle_scope": BUNDLE_SCOPE_SENTENCE,
            "reproduction": REPRODUCTION_DETAIL,
        },
    }


def build_bundle(
    *,
    task: TaskView,
    gate: TaskGateStatus,
    completion: ModuleCompletion,
    runs: Sequence[RunView],
    files: Sequence[WorkspaceFile],
) -> ProofBundle:
    """The document plus the digest a single-use approval binds to."""
    document = build_document(
        task=task, gate=gate, completion=completion, runs=runs, files=files
    )
    return ProofBundle(
        task_id=task.id,
        source_version_id=task.source_version_id,
        document=document,
        sha256=bundle_sha256(document),
    )


def render_json(document: dict[str, Any]) -> bytes:
    """Canonical JSON. Sorted keys, no whitespace, no timestamp of the copy."""
    return canonical_json_bytes(document)


def _markdown_table(rows: Sequence[tuple[str, str]]) -> list[str]:
    return [
        "| Alan | Deger |",
        "| --- | --- |",
        *(f"| {escape_markdown(name)} | {escape_markdown(value)} |" for name, value in rows),
        "",
    ]


def render_markdown(document: dict[str, Any]) -> bytes:
    """The human-readable format. Fixed sections, fixed order, ``\\n`` endings.

    A **summary**, and it says so: the JSON carries the same facts in a shape
    a checker can read, and both carry the artifact digests, because a summary
    nothing can be re-derived from is decoration.
    """
    task = document["task"]
    artifacts = document["artifacts"]
    claims = document["claims"]

    lines: list[str] = [
        "# Technocore Station - kanit paketi",
        "",
        f"- Bicim surumu: `{BUNDLE_VERSION}`",
        "",
        f"> {escape_markdown(document['notes']['hash_scope'])}",
        "",
        f"> {escape_markdown(document['notes']['bundle_scope'])}",
        "",
        "## Gorev",
        "",
        *_markdown_table(
            [
                ("Gorev id", str(task["id"])),
                ("Modul", str(task["module_id"])),
                ("Kaynak", str(task["source_id"])),
                ("Baslik", str(task["title"])),
                ("Durum", str(task["state"])),
                ("Icerik SHA-256", str(task["content_sha256"])),
                ("Icerik surumu", str(task["source_version_id"])),
            ]
        ),
        "## Artifactlar",
        "",
        *_markdown_table(
            [
                ("Dosya sayisi", str(artifacts["file_count"])),
                ("Toplam bayt", str(artifacts["total_bytes"])),
                ("Kume ozeti (SHA-256)", str(artifacts["set_sha256"])),
            ]
        ),
    ]

    if artifacts["files"]:
        lines += [
            "| Dosya | Bayt | SHA-256 |",
            "| --- | --- | --- |",
            *(
                f"| {escape_markdown(str(item['name']))} | {item['byte_count']} | "
                f"`{escape_markdown(str(item['sha256']))}` |"
                for item in artifacts["files"]
            ),
            "",
        ]
    else:
        lines += ["Calisma alaninda dosya yok.", ""]

    lines += ["## Dort alan", "", "| Alan | Durum | Isaretci |", "| --- | --- | --- |"]
    for entry in document["evidence_fields"]:
        lines.append(
            f"| {escape_markdown(str(entry['field']))} | "
            f"{escape_markdown(str(entry['state']))} | "
            f"`{escape_markdown(str(entry['ref_id']) or 'yok')}` |"
        )
    lines += [""]

    lines += [
        "## Uretilmeyen kayitlar",
        "",
        f"- Bagimsiz kontrol: `{claims['independent_check']['state']}` - "
        f"{escape_markdown(str(claims['independent_check']['detail']))}",
        f"- Cikis kodu: `{claims['exit_code']['state']}` - "
        f"{escape_markdown(str(claims['exit_code']['detail']))}",
        f"- Test sonucu: `{claims['test_result']['state']}` - "
        f"{escape_markdown(str(claims['test_result']['detail']))}",
        "",
        "## Calismalar",
        "",
    ]

    if document["runs"]:
        for run in document["runs"]:
            lines += [
                f"### `{escape_markdown(str(run['id']))}`",
                "",
                *_markdown_table(
                    [
                        ("Asama", str(run["phase"])),
                        ("Plan SHA-256", str(run["plan_sha256"])),
                        ("Basari olcutu", str(run["test_condition"])),
                        ("Test sonucu", str(run["test_result_state"])),
                        (
                            "Arac cagrisi",
                            f"{run['tool_calls_used']} / {run['max_tool_calls']}",
                        ),
                    ]
                ),
            ]
    else:
        lines += ["Kayitli calisma yok.", ""]

    lines += ["## Eksikler", ""]
    if document["missing"]:
        for entry in document["missing"]:
            lines.append(
                f"- `{escape_markdown(str(entry['key']))}` "
                f"({escape_markdown(str(entry['state']))}): "
                f"{escape_markdown(str(entry['detail']))}"
            )
    else:
        lines.append("Adlandirilmis bir eksik yok.")
    lines += [
        "",
        "## Yeniden uretme",
        "",
        escape_markdown(document["notes"]["reproduction"]),
        "",
    ]

    return "\n".join(lines).encode("utf-8")


def render(document: dict[str, Any], *, bundle_format: BundleFormat) -> bytes:
    """One of the two writers, or a refusal naming the closed set."""
    if bundle_format == "json":
        return render_json(document)
    if bundle_format == "markdown":
        return render_markdown(document)
    raise BundleFormatError(
        "Bilinmeyen paket bicimi. Yalnizca 'json' ve 'markdown' uretilir."
    )


__all__ = [
    "BUNDLE_DOMAIN",
    "BUNDLE_FORMATS",
    "BUNDLE_KIND",
    "BUNDLE_MEDIA_TYPE",
    "BUNDLE_STEM",
    "BUNDLE_SUFFIX",
    "BUNDLE_VERSION",
    "EXIT_CODE_DETAIL",
    "INDEPENDENT_CHECK_DETAIL",
    "MAX_BUNDLE_TEXT_CHARS",
    "NOT_IMPLEMENTED",
    "PRODUCT_SENTENCES",
    "REPRODUCTION_DETAIL",
    "BundleFormat",
    "BundleFormatError",
    "ProofBundle",
    "artifact_set_sha256",
    "assert_product_language",
    "build_bundle",
    "build_document",
    "bundle_sha256",
    "render",
    "render_json",
    "render_markdown",
    "safe_text",
]
