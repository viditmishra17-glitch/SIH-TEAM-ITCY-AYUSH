"""
M3 — Source adapters / snapshots (Build Manual section 6).

JOB:        obtain the seller listing and the official declaration.
INPUT:      product identifier / search hints.
OUTPUT:     normalized snapshots plus the raw response.
DONE WHEN:  a case can be replayed without the external service.
CONSTRAINT: cache every demo source response; live acquisition is optional and
            must never be on the demo's critical path.
"""

from app.pipeline.adapters.base import (
    Snapshot,
    SourceAdapter,
    SourceUnavailable,
)
from app.pipeline.adapters.ecommerce import get_ecommerce_adapter
from app.pipeline.adapters.official import get_official_adapter

__all__ = [
    "Snapshot",
    "SourceAdapter",
    "SourceUnavailable",
    "get_ecommerce_adapter",
    "get_official_adapter",
]
