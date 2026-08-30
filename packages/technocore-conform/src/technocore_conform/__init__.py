"""Technocore conformance package - PLACEHOLDER.

Stage 1 establishes only the *package boundary*. There is intentionally no
sweep, canonicalization, ``did:key`` or signing code here yet; that arrives in
Stage 2B (see PROJECT_STATUS.md).

Boundary rules, enforced by review and by the absence of imports below:

* This package imports **nothing** from ``station_api``, FastAPI, SQLAlchemy,
  SQLite or any Windows-specific module. It is plain, portable Python.
* It implements the specification in ``docs/protocol-contract.md``. It does
  **not** copy implementation lines out of ``vendor/technocore-reference/``,
  which is Apache-2.0; this package is MIT.
* ``vendor/technocore-reference/`` is a differential test *oracle* only, used
  from ``tests/conformance/``. It is never imported from here.

The contract this package will implement:

    message:  <room>|<nonce>|<swept_text>
    note:     <namespace>|<key>|<nonce>|<swept_value>

where the sweep replaces every character in Unicode category Cc, Cf, Cs, Co,
Zl or Zp with a single space and then trims the ends.
"""

from __future__ import annotations

__version__ = "0.0.1"

#: Roadmap stage that will implement this package.
IMPLEMENTED_IN_STAGE = "2B"

#: Field separator in every canonical string.
CANONICAL_SEPARATOR = "|"

__all__ = ["CANONICAL_SEPARATOR", "IMPLEMENTED_IN_STAGE", "__version__"]
