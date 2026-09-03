"""Composer: draft, sign, send.

Deliberately empty of re-exports. :mod:`station_api.technocore.service` needs
the verdict digest from :mod:`station_api.compose.approvals`, so a package
``__init__`` that pulled in :mod:`station_api.compose.service` - which imports
the technocore service in turn - would make that a circular import. Callers
name the module they want.
"""

from __future__ import annotations
