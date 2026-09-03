"""Building a ``Content-Disposition`` header that cannot say more than a name.

Station hands files to the browser rather than writing them to a path the
user chose (ADR-0003 9). That decision removes path traversal, symlinks,
reparse points and overwrite prompts from the product entirely - there is no
filesystem write to attack - and leaves exactly one thing to get right: the
header.

Until Package E that header was one raw f-string::

    f'attachment; filename="{filename}"'

Safe as written, because the only variable part was the base58 tail of a DID.
Package E puts a **room name** and a caller-chosen label in a download name,
so the assumption that made it safe stops holding, and the gap is closed with
a helper rather than with a second f-string that happens to be careful.

What the header can be made to do
---------------------------------
``"`` ends the quoted string, so the rest of the name becomes header
parameters. ``;`` starts a new parameter. A CR or LF splits the header - or,
on a server that rejects that, produces a 500 instead of a download. ``/``,
``\\`` and ``..`` are the browser's problem rather than ours, but a browser
that honours them writes somewhere nobody chose. A right-to-left override
makes ``report.exe`` render as ``report.txt`` in the save dialog. Non-ASCII
bytes in an unencoded ``filename`` parameter are simply undefined.

So the name is rebuilt from an allow-list rather than filtered
--------------------------------------------------------------
Everything that is not ``[A-Za-z0-9._-]`` becomes a hyphen. That is a
deliberately blunt rule: a deny-list of dangerous characters is a list of the
attacks someone thought of, and this is a header where being unimaginative is
free. Turkish names lose their diacritics in the *filename*; the file's
contents are untouched, and a download name is not a document title.

There is no ``filename*=UTF-8''...`` form here for the same reason: adding a
second, percent-encoded spelling of the same name would be a second parser to
be wrong about, to recover characters nobody needs in a filename.
"""

from __future__ import annotations

import re

#: Everything else becomes a separator. ASCII only, on purpose.
_ALLOWED = re.compile(r"[^A-Za-z0-9._-]+")

#: Runs of separators collapse, so a swept name does not become a row of
#: hyphens long enough to hide the extension off the end of a dialog.
_RUNS = re.compile(r"-{2,}")

#: Leading characters that make a name awkward or hidden.
_LEADING = "-._"

#: Longest stem kept. Windows' own limit is 255 for the whole name; this is
#: shorter so the suffix always survives and a dialog can show the end.
MAX_STEM_CHARS = 80

#: What a name that sanitises to nothing becomes.
DEFAULT_STEM = "indirme"


def safe_filename_stem(stem: str, *, fallback: str = DEFAULT_STEM) -> str:
    """Reduce an arbitrary string to a filename stem that carries no syntax.

    ``".."`` cannot survive: the dots are kept as characters but every
    separator is gone, and a stem that reduces to nothing but dots falls back.
    """
    swept = _ALLOWED.sub("-", stem)
    swept = _RUNS.sub("-", swept).strip(_LEADING)
    swept = swept[:MAX_STEM_CHARS].strip(_LEADING)
    if not swept or set(swept) <= set("."):
        return fallback
    return swept


def safe_download_filename(
    stem: str, *, suffix: str, fallback: str = DEFAULT_STEM
) -> str:
    """A complete, header-safe filename.

    ``suffix`` is a constant at every call site - it names the format the
    route produces - and is sanitised anyway, because "it is a constant
    today" is the property that stops being true first.
    """
    clean_suffix = _ALLOWED.sub("", suffix)
    if clean_suffix and not clean_suffix.startswith("."):
        clean_suffix = f".{clean_suffix}"
    return f"{safe_filename_stem(stem, fallback=fallback)}{clean_suffix}"


def content_disposition(filename: str) -> str:
    """The header value for one attachment.

    The name is sanitised **here** as well as by the caller. Redundant by
    design: this is the function whose output goes on the wire, and a caller
    that forgets is the case worth surviving.
    """
    return f'attachment; filename="{safe_download_filename(filename, suffix="")}"'


__all__ = [
    "DEFAULT_STEM",
    "MAX_STEM_CHARS",
    "content_disposition",
    "safe_download_filename",
    "safe_filename_stem",
]
