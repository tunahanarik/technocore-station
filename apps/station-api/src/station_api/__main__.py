"""Entry point: ``python -m station_api``."""

from __future__ import annotations

import sys

from station_api.launcher import main

if __name__ == "__main__":
    sys.exit(main())
