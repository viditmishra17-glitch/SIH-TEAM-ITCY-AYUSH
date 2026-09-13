"""Unit tests for M4 — normalization and value comparison."""

from __future__ import annotations

import pytest

from app.engine.compare import Comparison, compare_values
from app.pipeline.normalize import (
    normalize_date,
    normalize_field,
    normalize_identifier,
    normalize_money,
    normalize_name,
    normalize_quantity,
)


class TestMoney:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("MRP Rs. 99.00/-", 99.0),
            ("₹99", 99.0),
            ("INR 79", 79.0),
            ("Rs 1,299.00 (incl. of all taxes)", 1299.0),
            ("Maximum Retail Price: 249", 249.0),
            ("M.R.P. ₹ 1,05,000", 105000.0),  # Indian lakh grouping
        ],
    )
    def test_parses_amount(self, raw, expected):
        result = normalize_money(raw)
        assert result is not None
        assert result["amount"] == expected

    @pytest.mark.parametrize("raw", ["", None, "price on request", "MRP: illegible"])
    def test_returns_none_rather_than_guessing(self, raw):
        assert normalize_money(raw) is None

    def test_currency_detected(self):
        assert normalize_money("$12.50")["currency"] == "USD"
        assert normalize_money("Rs 12.50")["currency"] == "INR"


class TestQuantity:
    @pytest.mark.parametrize(
        "raw,value,unit",
        [
            ("500 g", 500.0, "g"),
            ("0.5 kg", 500.0, "g"),
            ("500gm", 500.0, "g"),
            ("1 kg", 1000.0, "g"),
            ("Net Wt. 1kg", 1000.0, "g"),
            ("1 L", 1000.0, "ml"),
            ("750 ml", 750.0, "ml"),
            ("2 x 250 ml", 500.0, "ml"),
            ("12 N", 12.0, "pcs"),
            ("250 mg", 0.25, "g"),
        ],
    )
    def test_converts_to_base_unit(self, raw, value, unit):
        result = normalize_quantity(raw)
        assert result is not None
        assert result["value"] == pytest.approx(value)
        assert result["unit"] == unit

    @pytest.mark.parametrize("raw", ["", None, "500 blorp", "as marked", "0 g"])
    def test_rejects_unparseable(self, raw):
        assert normalize_quantity(raw) is None

    def test_equivalent_representations_compare_equal(self):
        assert (
            compare_values("net_quantity", normalize_quantity("1 kg"), normalize_quantity("1000 g"))
            is Comparison.EQUAL
        )

    def test_different_values_stay_different(self):
        assert (
            compare_values("net_quantity", normalize_quantity("500 g"), normalize_quantity("450 g"))
            is Comparison.DIFFERENT
        )

    def test_mass_and_volume_are_never_equal(self):
        """500 g vs 500 ml must be INCOMPARABLE, not a false match."""
        assert (
            compare_values("net_quantity", normalize_quantity("500 g"), normalize_quantity("500 ml"))
            is Comparison.INCOMPARABLE
        )


class TestDates:
    @pytest.mark.parametrize(
        "raw,iso,precision",
        [
            ("2025-12-01", "2025-12-01", "day"),
            ("01/12/2025", "2025-12-01", "day"),
            ("15.03.2026", "2026-03-15", "day"),
            ("MFG: DEC 2025", "2025-12-01", "month"),
            ("Best Before 12/2026", "2026-12-01", "month"),
            ("2027", "2027-01-01", "year"),
        ],
    )
    def test_parses(self, raw, iso, precision):
        result = normalize_date(raw)
        assert result == {"iso": iso, "precision": precision}

    @pytest.mark.parametrize("raw", ["", None, "12 months from packing", "see cap"])
    def test_rejects_unparseable(self, raw):
        assert normalize_date(raw) is None

    def test_compares_at_coarser_precision(self):
        """A label printed 'DEC 2025' does not disagree with '01/12/2025'."""
        assert (
            compare_values(
                "manufacturing_date", normalize_date("DEC 2025"), normalize_date("01/12/2025")
            )
            is Comparison.EQUAL
        )

    def test_different_months_differ(self):
        assert (
            compare_values(
                "manufacturing_date", normalize_date("DEC 2025"), normalize_date("JAN 2026")
            )
            is Comparison.DIFFERENT
        )

    def test_invalid_calendar_date_is_rejected(self):
        assert normalize_date("31/02/2026") is None


class TestNames:
    def test_legal_suffixes_are_ignored(self):
        left = normalize_name("Sunrise Foods Pvt. Ltd.")
        right = normalize_name("SUNRISE FOODS PRIVATE LIMITED")
        assert left["canonical"] == right["canonical"] == "sunrise foods"
        assert compare_values("manufacturer_name", left, right) is Comparison.EQUAL

    def test_different_entities_differ(self):
        assert (
            compare_values(
                "manufacturer_name",
                normalize_name("Greyline Imports LLP"),
                normalize_name("Meridian Global Traders LLP"),
            )
            is Comparison.DIFFERENT
        )

    def test_display_value_is_preserved(self):
        assert normalize_name("Sunrise Foods Pvt. Ltd.")["display"] == "Sunrise Foods Pvt. Ltd."


class TestIdentifiers:
    def test_punctuation_is_stripped(self):
        assert normalize_identifier("8901234-567890")["canonical"] == "8901234567890"

    def test_case_is_normalized(self):
        assert normalize_identifier("sr-2512-a")["canonical"] == "SR2512A"

    def test_identifiers_must_match_exactly(self):
        assert (
            compare_values(
                "identifier", normalize_identifier("8901234567890"), normalize_identifier("8901234567891")
            )
            is Comparison.DIFFERENT
        )


class TestComparisonSafety:
    def test_missing_side_is_incomparable(self):
        assert compare_values("mrp", normalize_money("Rs 99"), None) is Comparison.INCOMPARABLE

    def test_non_dict_input_is_incomparable(self):
        """Defensive: a raw string must never be treated as a normalized value."""
        assert compare_values("mrp", "99", "99") is Comparison.INCOMPARABLE

    def test_dispatch_uses_field_kind(self):
        assert normalize_field("mrp", "Rs 99")["amount"] == 99.0
        assert normalize_field("net_quantity", "1 kg")["unit"] == "g"
        assert normalize_field("manufacturing_date", "DEC 2025")["precision"] == "month"
