"""
E-commerce adapter.

Cached snapshots are the default and the demo path. A live HTTP adapter is
provided as a seam, disabled unless ``TRIVERIFY_LIVE_SOURCES=1`` and a
connector is configured — the manual is explicit that live marketplace
crawling must never block the demo (section 17, P2).
"""

from __future__ import annotations

from typing import Any

from app.core import config
from app.pipeline.adapters.base import FixtureAdapter, Snapshot, SourceUnavailable


class LiveEcommerceAdapter:
    """Placeholder for a policy-compliant seller-data connector.

    Intentionally not implemented: scraping behaviour differs per platform and
    per terms of service. Wire a real partner/affiliate API in here; the rest
    of the system needs no changes because it only ever sees a ``Snapshot``.
    """

    name = "live-ecommerce"

    def fetch(self, identifier: str, hints: dict[str, Any] | None = None) -> Snapshot:
        raise SourceUnavailable(
            "Live e-commerce acquisition is not configured. "
            "Set TRIVERIFY_LIVE_SOURCES=1 and register a compliant connector."
        )


class EcommerceAdapter:
    """Cache-first adapter with an optional live fallback."""

    name = "ecommerce"

    def __init__(self) -> None:
        self._fixture = FixtureAdapter(config.LISTINGS_DIR, "e-commerce listing")
        self._live = LiveEcommerceAdapter()

    def fetch(self, identifier: str, hints: dict[str, Any] | None = None) -> Snapshot:
        if self._fixture.has(identifier):
            return self._fixture.fetch(identifier, hints)
        if config.LIVE_SOURCES_ENABLED:
            return self._live.fetch(identifier, hints)
        raise SourceUnavailable(
            f"No cached seller listing for {identifier!r} and live acquisition is disabled."
        )


_adapter: EcommerceAdapter | None = None


def get_ecommerce_adapter() -> EcommerceAdapter:
    global _adapter
    if _adapter is None:
        _adapter = EcommerceAdapter()
    return _adapter
