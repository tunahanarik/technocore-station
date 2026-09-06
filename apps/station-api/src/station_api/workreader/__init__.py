"""The work scan's model lane: a stranger's line in, a closed verdict out.

ADR-0014. This package exists as a package rather than as two functions inside
:mod:`station_api.workscan` for one reason, and it is the reason ADR-0013 gave
for keeping ``budget.py`` and ``model_calls.py`` apart: a rule is not edited to
fit the code.

``tests/security/test_work_scan_candidates.py::
test_the_package_calls_no_model_and_imports_no_completion_path`` says the scan
package imports nothing that can reach a provider. That sentence is still
true and is still worth keeping true - the scan package parses documents,
sweeps text, applies the prohibition registry and builds candidates, and none
of that should be able to spend money. So the money is spent here, and
:mod:`station_api.workscan.service` names only the
:class:`~station_api.workscan.reading.LineReader` protocol.

What this package may reach
----------------------------
``station_api.opencode.service``, ``station_api.opencode.planner`` and
``station_api.opencode.errors`` - the same three
``tests/security/test_planner_boundary.py`` allows the planning package, and
for the same reason: this tree may *ask the reviewed connection for a turn*
and may not assemble a request beside it. ``station_api.opencode.client``,
``httpx``, ``socket`` and ``ssl`` are refused here, and
``tests/security/test_work_reader_boundary.py`` reads the syntax tree rather
than trusting this paragraph.

What it may not do
-------------------
Execute anything, schedule anything, open a file, name an address, write a
row, start a run or approve a plan. It turns bytes into ``(seq, signal)``
pairs. Everything a candidate then says is written in
:data:`station_api.workscan.candidates.SIGNALS` and reviewed there.
"""

from __future__ import annotations

from station_api.workreader.errors import ReadingProtocolError, WorkReaderError
from station_api.workreader.service import WorkReaderService

__all__ = ["ReadingProtocolError", "WorkReaderError", "WorkReaderService"]
