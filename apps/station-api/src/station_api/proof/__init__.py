"""The proof workspace (Package H3).

Four modules, and none of them owns anything the rest of the product already
owns. :mod:`station_api.proof.bundle` builds a deterministic document out of
values other services computed; :mod:`station_api.proof.approvals` holds the
single-use consent that document's delivery needs;
:mod:`station_api.proof.language` refuses the claims this package must not
make; and :mod:`station_api.proof.service` puts the three together.

There is no database table here, no file root, no outbound client, no signer
and no vault. The package reads, assembles and refuses.
"""

from __future__ import annotations

__all__: list[str] = []
