"""
M4 — Field normalization (Build Manual section 6).

JOB:    make values from three independent surfaces comparable.
INPUT:  raw field strings from photo OCR, seller listing, official record.
OUTPUT: canonical values + a stable display string.
DONE:   equivalent representations compare equal, genuinely different values
        stay different.

Design rules that keep this bug-free:

* Every normalizer is a pure function. No I/O, no globals, no clocks.
* A normalizer NEVER guesses. If it cannot parse a value it returns ``None``,
  which the engine turns into REVIEW. Silent coercion is how false
  "compliant" verdicts get created.
* Normalized values are plain JSON types so they round-trip through the
  database and the API unchanged.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from app.engine.vocabulary import FIELD_KINDS, ValueKind

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")

#: OCR routinely confuses these inside otherwise-numeric strings.
_DIGIT_CONFUSIONS = {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5"}


def clean_text(value: str | None) -> str:
    """Unicode-normalize, strip zero-width junk, collapse whitespace."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("​", "").replace("﻿", "")
    text = text.replace("–", "-").replace("—", "-")
    return _WS_RE.sub(" ", text).strip()


def _fix_numeric_confusions(token: str) -> str:
    """Apply OCR digit confusions only to tokens that are mostly digits.

    Guard rail: we must never turn the word "Ol" in a company name into "01".
    """
    digits = sum(ch.isdigit() for ch in token)
    if digits == 0 or digits < len(token) / 2:
        return token
    return "".join(_DIGIT_CONFUSIONS.get(ch, ch) for ch in token)


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOLS = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "r": "INR",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "£": "GBP",
}

_MONEY_NUMBER_RE = re.compile(r"(\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")


def normalize_money(value: str | None) -> dict[str, Any] | None:
    """'MRP Rs. 1,299.00/- (incl. of all taxes)' -> {'currency','amount'}."""
    text = clean_text(value)
    if not text:
        return None

    lowered = text.lower()
    currency = "INR"
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in lowered:
            currency = code
            break

    # Drop currency tokens and label words so "MRP Rs. 99" and "99" parse
    # identically, and so nothing legitimate is left touching the number.
    stripped = re.sub(r"[₹$€£]", " ", lowered)
    stripped = re.sub(
        r"\b(mrp|m\.?\s?r\.?\s?p\.?|maximum\s+retail\s+price|retail\s+sale\s+price|"
        r"price|rs|inr|rupees?|incl|inclusive|of|all|taxes|tax)\b",
        " ",
        stripped,
    )
    stripped = stripped.replace("/-", " ")
    stripped = _fix_numeric_confusions(stripped) if any(c.isdigit() for c in stripped) else stripped

    match = _MONEY_NUMBER_RE.search(stripped)
    if not match:
        return None

    # Reject a number with a letter fused to it. Garbled OCR such as
    # "Rs. 4Z9.OO" would otherwise parse as a confident Rs. 4.00 — a wrong
    # value that looks right is far more dangerous than no value at all.
    start, end = match.span(1)
    if (start > 0 and stripped[start - 1].isalpha()) or (
        end < len(stripped) and stripped[end].isalpha()
    ):
        return None

    number = match.group(1).replace(",", "")
    try:
        amount = round(float(number), 2)
    except ValueError:
        return None
    if amount < 0:
        return None

    return {"currency": currency, "amount": amount}


def format_money(norm: dict[str, Any] | None) -> str | None:
    if not norm:
        return None
    symbol = {"INR": "Rs.", "USD": "$", "EUR": "€", "GBP": "£"}.get(
        norm.get("currency", "INR"), ""
    )
    amount = norm.get("amount")
    if amount is None:
        return None
    return f"{symbol} {amount:,.2f}".strip()


# ---------------------------------------------------------------------------
# Quantity
# ---------------------------------------------------------------------------

#: Canonical base unit per dimension: mass -> g, volume -> ml, count -> pcs.
_UNIT_TABLE: dict[str, tuple[str, float, str]] = {
    # token: (dimension, factor to base, base unit)
    "mg": ("mass", 0.001, "g"),
    "g": ("mass", 1.0, "g"),
    "gm": ("mass", 1.0, "g"),
    "gms": ("mass", 1.0, "g"),
    "gram": ("mass", 1.0, "g"),
    "grams": ("mass", 1.0, "g"),
    "kg": ("mass", 1000.0, "g"),
    "kgs": ("mass", 1000.0, "g"),
    "kilogram": ("mass", 1000.0, "g"),
    "kilograms": ("mass", 1000.0, "g"),
    "ml": ("volume", 1.0, "ml"),
    "milliliter": ("volume", 1.0, "ml"),
    "millilitre": ("volume", 1.0, "ml"),
    "cl": ("volume", 10.0, "ml"),
    "l": ("volume", 1000.0, "ml"),
    "lt": ("volume", 1000.0, "ml"),
    "ltr": ("volume", 1000.0, "ml"),
    "litre": ("volume", 1000.0, "ml"),
    "liter": ("volume", 1000.0, "ml"),
    "litres": ("volume", 1000.0, "ml"),
    "liters": ("volume", 1000.0, "ml"),
    "n": ("count", 1.0, "pcs"),
    "no": ("count", 1.0, "pcs"),
    "nos": ("count", 1.0, "pcs"),
    "pc": ("count", 1.0, "pcs"),
    "pcs": ("count", 1.0, "pcs"),
    "piece": ("count", 1.0, "pcs"),
    "pieces": ("count", 1.0, "pcs"),
    "unit": ("count", 1.0, "pcs"),
    "units": ("count", 1.0, "pcs"),
}

_QUANTITY_RE = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zA-Z]+\.?)",
)

#: "2 x 250 g" style multipacks.
_MULTIPACK_RE = re.compile(
    r"(?P<count>\d+)\s*[x×*]\s*(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zA-Z]+\.?)",
    re.IGNORECASE,
)


def normalize_quantity(value: str | None) -> dict[str, Any] | None:
    """'1 kg' / '1000g' / '2 x 500 ml' -> canonical base-unit quantity.

    Returns ``{'value', 'unit', 'dimension', 'display_value', 'display_unit'}``
    where ``value``/``unit`` are always in the canonical base unit so that
    ``1 kg`` and ``1000 g`` compare equal.
    """
    text = clean_text(value)
    if not text:
        return None
    lowered = text.lower().replace("net wt", " ").replace("net weight", " ")
    lowered = lowered.replace("net qty", " ").replace("net quantity", " ")

    pack_count = 1
    match: re.Match[str] | None = _MULTIPACK_RE.search(lowered)
    if match:
        pack_count = int(match.group("count"))
    else:
        match = _QUANTITY_RE.search(lowered)
    if not match:
        return None

    raw_unit = match.group("unit").rstrip(".").lower()
    entry = _UNIT_TABLE.get(raw_unit)
    if entry is None:
        return None
    dimension, factor, base_unit = entry

    raw_value = match.group("value").replace(",", ".")
    try:
        magnitude = float(raw_value)
    except ValueError:
        return None
    if magnitude <= 0:
        return None

    total = round(magnitude * factor * pack_count, 4)
    return {
        "value": total,
        "unit": base_unit,
        "dimension": dimension,
        "display_value": round(magnitude * pack_count, 4),
        "display_unit": raw_unit,
        "pack_count": pack_count,
    }


def format_quantity(norm: dict[str, Any] | None) -> str | None:
    if not norm:
        return None
    value = norm.get("value")
    unit = norm.get("unit")
    if value is None or unit is None:
        return None
    if float(value).is_integer():
        return f"{int(value)} {unit}"
    return f"{value:g} {unit}"


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")
_MON_YEAR_RE = re.compile(r"\b([a-z]{3,9})[\s./\-]*(\d{2,4})\b")
_MY_NUM_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{2,4})\b")
_YEAR_ONLY_RE = re.compile(r"\b(20\d{2})\b")


def _expand_year(raw: str) -> int:
    year = int(raw)
    if year < 100:
        # Packaged-goods dates: 70-99 -> 1970s+, otherwise 2000s.
        return 1900 + year if year >= 70 else 2000 + year
    return year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def normalize_date(value: str | None) -> dict[str, Any] | None:
    """Parse label dates to ISO with explicit granularity.

    Packaged goods very often carry only month+year ("DEC 2025"), so the
    result records ``precision`` as ``day``, ``month`` or ``year``. Comparison
    is then done at the coarser of the two precisions instead of pretending a
    missing day matched.
    """
    text = clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    lowered = re.sub(
        r"\b(mfg|mfd|manufactured|manufacturing|packed|packing|pkd|exp|expiry|expires|"
        r"best before|use by|date of|on|dt)\b",
        " ",
        lowered,
    )
    lowered = _WS_RE.sub(" ", lowered).strip()

    # A full date pattern that matched but does not denote a real calendar day
    # (e.g. "31/02/2026") is rejected outright. Falling through to a coarser
    # reading would silently turn nonsense into a usable-looking value.
    match = _ISO_RE.search(lowered)
    if match:
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return {"iso": parsed.isoformat(), "precision": "day"} if parsed else None

    match = _DMY_RE.search(lowered)
    if match:
        first, second, third = match.group(1), match.group(2), match.group(3)
        year = _expand_year(third)
        day, month = int(first), int(second)
        # Indian labels are day-first; fall back to month-first only if the
        # day-first reading is impossible.
        parsed = _safe_date(year, month, day)
        if parsed is None:
            parsed = _safe_date(year, day, month)
        return {"iso": parsed.isoformat(), "precision": "day"} if parsed else None

    match = _MON_YEAR_RE.search(lowered)
    if match:
        month = _MONTHS.get(match.group(1))
        if month:
            year = _expand_year(match.group(2))
            parsed = _safe_date(year, month, 1)
            if parsed:
                return {"iso": parsed.isoformat(), "precision": "month"}

    match = _MY_NUM_RE.search(lowered)
    if match:
        month = int(match.group(1))
        if 1 <= month <= 12:
            year = _expand_year(match.group(2))
            parsed = _safe_date(year, month, 1)
            if parsed:
                return {"iso": parsed.isoformat(), "precision": "month"}

    match = _YEAR_ONLY_RE.search(lowered)
    if match:
        return {"iso": f"{match.group(1)}-01-01", "precision": "year"}

    return None


def format_date(norm: dict[str, Any] | None) -> str | None:
    if not norm or not norm.get("iso"):
        return None
    try:
        parsed = date.fromisoformat(norm["iso"])
    except (ValueError, TypeError):
        return None
    precision = norm.get("precision", "day")
    if precision == "year":
        return parsed.strftime("%Y")
    if precision == "month":
        return parsed.strftime("%b %Y").upper()
    return parsed.strftime("%d %b %Y").upper()


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

_LEGAL_SUFFIXES = {
    "pvt", "private", "ltd", "limited", "llp", "inc", "incorporated", "corp",
    "corporation", "co", "company", "plc", "gmbh", "sa", "bv", "industries",
    "india", "and", "&",
}

_NAME_NOISE_RE = re.compile(r"[^a-z0-9\s]")


def normalize_name(value: str | None) -> dict[str, Any] | None:
    """Canonicalize an entity name into comparable tokens.

    'Sunrise Foods Pvt. Ltd.' and 'SUNRISE FOODS PRIVATE LIMITED' both become
    tokens ``['sunrise', 'foods']``.
    """
    text = clean_text(value)
    if not text:
        return None
    lowered = _NAME_NOISE_RE.sub(" ", text.lower())
    tokens = [t for t in lowered.split() if t]
    core = [t for t in tokens if t not in _LEGAL_SUFFIXES]
    if not core:
        core = tokens
    if not core:
        return None
    return {"canonical": " ".join(core), "tokens": core, "display": text}


def format_name(norm: dict[str, Any] | None) -> str | None:
    if not norm:
        return None
    return norm.get("display") or norm.get("canonical")


# ---------------------------------------------------------------------------
# Free text / identifiers
# ---------------------------------------------------------------------------

_DIGITS_RE = re.compile(r"\d+")


def normalize_text(value: str | None) -> dict[str, Any] | None:
    text = clean_text(value)
    if not text:
        return None
    compact = re.sub(r"[^a-z0-9]", "", text.lower())
    return {"canonical": compact, "display": text, "digits": "".join(_DIGITS_RE.findall(text))}


def normalize_identifier(value: str | None) -> dict[str, Any] | None:
    text = clean_text(value)
    if not text:
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    if not compact:
        return None
    return {"canonical": compact, "display": text}


def format_text(norm: dict[str, Any] | None) -> str | None:
    if not norm:
        return None
    return norm.get("display") or norm.get("canonical")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_NORMALIZERS = {
    ValueKind.MONEY: normalize_money,
    ValueKind.QUANTITY: normalize_quantity,
    ValueKind.DATE: normalize_date,
    ValueKind.NAME: normalize_name,
    ValueKind.TEXT: normalize_text,
    ValueKind.IDENTIFIER: normalize_identifier,
}

_FORMATTERS = {
    ValueKind.MONEY: format_money,
    ValueKind.QUANTITY: format_quantity,
    ValueKind.DATE: format_date,
    ValueKind.NAME: format_name,
    ValueKind.TEXT: format_text,
    ValueKind.IDENTIFIER: format_text,
}


def normalize_field(field_name: str, value: str | None) -> dict[str, Any] | None:
    """Normalize ``value`` according to the canonical kind of ``field_name``."""
    kind = FIELD_KINDS.get(field_name, ValueKind.TEXT)
    normalizer = _NORMALIZERS[kind]
    return normalizer(value)


def display_field(field_name: str, norm: dict[str, Any] | None) -> str | None:
    """Human-readable rendering of a normalized value."""
    kind = FIELD_KINDS.get(field_name, ValueKind.TEXT)
    return _FORMATTERS[kind](norm)
