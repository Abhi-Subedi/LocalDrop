"""LocalDrop — self-hosted, local-network-first file sharing.

The package version lives in `localdrop.__about__` (single source of truth) and
is re-exported here for convenience: `from localdrop import __version__`.
"""

from __future__ import annotations

from .__about__ import __version__

__all__ = ["__version__"]
