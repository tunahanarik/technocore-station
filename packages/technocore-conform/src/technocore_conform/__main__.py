"""``python -m technocore_conform``.

The same entry point as the ``technocore-conform`` console script, for use
when the package is on the path but its scripts directory is not.
"""

from __future__ import annotations

from technocore_conform.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
