"""
Value comparison with explicit tolerances.

Separated from the rules so that "are these two values the same?" is one
testable decision, made identically everywhere.

Every comparison returns one of three answers — never a bare boolean:

    EQUAL         the two values are the same within configured tolerance
    DIFFERENT     the two values genuinely disagree
    INCOMPARABLE  at least one side could not be normalized, or the two are
                  not of the same kind (e.g. mass vs volume)

INCOMPARABLE is the important one: it becomes REVIEW, never PASS.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from app.core import config
from app.engine.vocabulary import FIELD_KINDS, ValueKind


class Comparison(str, Enum):
    EQUAL = "EQUAL"
    DIFFERENT = "DIFFERENT"
    INCOMPARABLE = "INCOMPARABLE"


def _compare_money(a: dict[str, Any], b: dict[str, Any]) -> Comparison:
    if a.get("currency") != b.get("currency"):
        return Comparison.INCOMPARABLE
    left, right = a.get("amount"), b.get("amount")
    if left is None or right is None:
        return Comparison.INCOMPARABLE
    if abs(float(left) - float(right)) <= config.MONEY_TOLERANCE:
        return Comparison.EQUAL
    return Comparison.DIFFERENT


def _compare_quantity(a: dict[str, Any], b: dict[str, Any]) -> Comparison:
    # 500 g vs 500 ml must never be called equal.
    if a.get("dimension") != b.get("dimension"):
        return Comparison.INCOMPARABLE
    left, right = a.get("value"), b.get("value")
    if left is None or right is None:
        return Comparison.INCOMPARABLE
    left, right = float(left), float(right)
    scale = max(abs(left), abs(right), 1e-9)
    if abs(left - right) / scale <= config.QUANTITY_REL_TOLERANCE:
        return Comparison.EQUAL
    return Comparison.DIFFERENT


_PRECISION_RANK = {"year": 0, "month": 1, "day": 2}


def _compare_date(a: dict[str, Any], b: dict[str, Any]) -> Comparison:
    try:
        left = date.fromisoformat(a["iso"])
        right = date.fromisoformat(b["iso"])
    except (KeyError, TypeError, ValueError):
        return Comparison.INCOMPARABLE

    # Compare at the coarser of the two precisions. A label printed "DEC 2025"
    # genuinely does not tell us the day, so demanding day equality would
    # invent a mismatch.
    rank = min(
        _PRECISION_RANK.get(a.get("precision", "day"), 2),
        _PRECISION_RANK.get(b.get("precision", "day"), 2),
    )
    if rank == 0:
        return Comparison.EQUAL if left.year == right.year else Comparison.DIFFERENT
    if rank == 1:
        same = (left.year, left.month) == (right.year, right.month)
        return Comparison.EQUAL if same else Comparison.DIFFERENT
    return Comparison.EQUAL if left == right else Comparison.DIFFERENT


def _compare_name(a: dict[str, Any], b: dict[str, Any]) -> Comparison:
    left = a.get("canonical")
    right = b.get("canonical")
    if not left or not right:
        return Comparison.INCOMPARABLE
    if left == right:
        return Comparison.EQUAL

    left_tokens = set(a.get("tokens") or left.split())
    right_tokens = set(b.get("tokens") or right.split())
    if not left_tokens or not right_tokens:
        return Comparison.INCOMPARABLE

    overlap = len(left_tokens & right_tokens)
    ratio = overlap / min(len(left_tokens), len(right_tokens))
    if ratio >= config.NAME_MATCH_THRESHOLD:
        return Comparison.EQUAL
    return Comparison.DIFFERENT


def _compare_canonical(a: dict[str, Any], b: dict[str, Any]) -> Comparison:
    left = a.get("canonical")
    right = b.get("canonical")
    if not left or not right:
        return Comparison.INCOMPARABLE
    return Comparison.EQUAL if left == right else Comparison.DIFFERENT


_COMPARATORS = {
    ValueKind.MONEY: _compare_money,
    ValueKind.QUANTITY: _compare_quantity,
    ValueKind.DATE: _compare_date,
    ValueKind.NAME: _compare_name,
    ValueKind.TEXT: _compare_canonical,
    ValueKind.IDENTIFIER: _compare_canonical,
}


def compare_values(
    field_name: str, left: Any | None, right: Any | None
) -> Comparison:
    """Compare two *normalized* values for ``field_name``."""
    if left is None or right is None:
        return Comparison.INCOMPARABLE
    if not isinstance(left, dict) or not isinstance(right, dict):
        # Defensive: anything that is not a normalized dict cannot be trusted.
        return Comparison.INCOMPARABLE
    kind = FIELD_KINDS.get(field_name, ValueKind.TEXT)
    return _COMPARATORS[kind](left, right)
