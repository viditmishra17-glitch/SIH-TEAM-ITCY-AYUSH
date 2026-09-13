"""
Official record adapter (e-Maap / CLMS style registered declarations).

Same shape as the e-commerce adapter: cached snapshots are the demo path, a
live connector is a seam. A missing official record is surfaced explicitly and
routed to review — the manual is emphatic that an absent record is *not*
evidence of compliance (section 19).
"""

from __future__ import annotations

from typing import Any

from app.core import config
from app.pipeline.adapters.base import FixtureAdapter, Snapshot, SourceUnavailable


class LiveOfficialAdapter:
    """Placeholder for the government registry connector."""

    name = "live-official"

    def fetch(self, identifier: str, hints: dict[str, Any] | None = None) -> Snapshot:
        raise SourceUnavailable(
            "Live official-registry lookup is not configured. "
            "Set TRIVERIFY_LIVE_SOURCES=1 and register e-Maap/CLMS credentials."
        )


class OfficialAdapter:
    name = "official"

    def __init__(self) -> None:
        self._fixture = FixtureAdapter(config.OFFICIAL_DIR, "official record")
        self._live = LiveOfficialAdapter()

    def fetch(self, identifier: str, hints: dict[str, Any] | None = None) -> Snapshot:
        if self._fixture.has(identifier):
            return self._fixture.fetch(identifier, hints)
        if config.LIVE_SOURCES_ENABLED:
            return self._live.fetch(identifier, hints)
        raise SourceUnavailable(
            f"No registered declaration found for {identifier!r}. "
            "A missing official record is not evidence of compliance."
        )


_adapter: OfficialAdapter | None = None


def get_official_adapter() -> OfficialAdapter:
    global _adapter
    if _adapter is None:
        _adapter = OfficialAdapter()
    return _adapter
