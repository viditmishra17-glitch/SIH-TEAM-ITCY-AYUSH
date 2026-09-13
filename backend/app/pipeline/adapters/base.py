"""Shared adapter contract."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.engine.vocabulary import CANONICAL_FIELDS
from app.pipeline.normalize import clean_text, normalize_field


class SourceUnavailable(Exception):
    """The source could not be reached or has no record for this product.

    This is a *normal* outcome, not a crash. The engine turns it into an
    explicit "source missing" state and routes affected rules to REVIEW —
    never to PASS.
    """


@dataclass
class Snapshot:
    """A point-in-time capture of one external source."""

    source: str
    url_or_id: str | None
    captured_at: datetime
    raw_json: dict[str, Any]
    is_live: bool = False
    fields: dict[str, str] = field(default_factory=dict)

    def normalized_fields(self) -> dict[str, dict[str, Any] | None]:
        """Normalize every declared field using the canonical vocabulary."""
        out: dict[str, dict[str, Any] | None] = {}
        for name, raw in self.fields.items():
            if name not in CANONICAL_FIELDS:
                continue
            text = clean_text(raw)
            if not text:
                continue
            out[name] = normalize_field(name, text)
        return out


class SourceAdapter(Protocol):
    name: str

    def fetch(self, identifier: str, hints: dict[str, Any] | None = None) -> Snapshot: ...


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class FixtureAdapter:
    """Serves committed snapshots from a directory of JSON files.

    Each file is ``<identifier>.json`` and looks like::

        {
          "source": "DemoMart",
          "url_or_id": "https://example.invalid/p/SR-1KG",
          "captured_at": "2026-09-01T10:00:00Z",
          "fields": {"mrp": "Rs. 79", "net_quantity": "1 kg"},
          "raw": { ...whatever the source actually returned... }
        }
    """

    name = "fixture"

    def __init__(self, directory: Path, default_source: str) -> None:
        self.directory = Path(directory)
        self.default_source = default_source

    @staticmethod
    def _key(identifier: str) -> str:
        return "".join(
            ch if ch.isalnum() or ch in "-_" else "_" for ch in str(identifier).strip().upper()
        )

    def has(self, identifier: str) -> bool:
        return (self.directory / f"{self._key(identifier)}.json").is_file()

    def fetch(self, identifier: str, hints: dict[str, Any] | None = None) -> Snapshot:
        path = self.directory / f"{self._key(identifier)}.json"
        if not path.is_file():
            raise SourceUnavailable(
                f"No cached {self.default_source} snapshot for identifier {identifier!r}."
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SourceUnavailable(f"Cached snapshot unreadable: {exc}") from exc

        fields = {
            str(k): str(v)
            for k, v in (payload.get("fields") or {}).items()
            if v is not None and str(v).strip()
        }
        if not fields:
            raise SourceUnavailable(
                f"Cached {self.default_source} snapshot for {identifier!r} declares no fields."
            )

        return Snapshot(
            source=payload.get("source", self.default_source),
            url_or_id=payload.get("url_or_id"),
            captured_at=_parse_timestamp(payload.get("captured_at")),
            raw_json=payload.get("raw") or payload,
            is_live=False,
            fields=fields,
        )
