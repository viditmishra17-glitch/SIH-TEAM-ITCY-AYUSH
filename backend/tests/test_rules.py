"""
Rule-engine tests: every mismatch combination across the three layers.

These use synthetic layers rather than the database so each rule's behaviour
is isolated from ingestion.
"""

from __future__ import annotations

import pytest

from app.core import config
from app.engine.reconcile import FieldValue, LayerData, reconcile
from app.engine.rules import LISTING, OFFICIAL, PHOTO
from app.engine.vocabulary import Classification, FieldStatus, RuleStatus
from app.pipeline.normalize import normalize_field

BASE = {
    "mrp": "Rs. 99.00",
    "net_quantity": "1 kg",
    "manufacturer_name": "Sunrise Foods Pvt Ltd",
    "consumer_care": "care@sunrise.example 1800-123-4567",
    "manufacturing_date": "DEC 2025",
    "product_name": "Sunrise Gold Chakki Atta",
    "identifier": "8901234567890",
}


def layer(name: str, values: dict, confidence: float = 0.95, **kwargs) -> LayerData:
    return LayerData(
        layer=name,
        fields={
            key: FieldValue(
                raw=value,
                norm=normalize_field(key, value),
                confidence=confidence,
                evidence_id=f"EV-{name[:2]}-{key}",
            )
            for key, value in values.items()
        },
        **kwargs,
    )


def three_layers(photo=None, listing=None, official=None, photo_conf=0.95):
    return {
        PHOTO: layer(PHOTO, photo if photo is not None else BASE, photo_conf),
        LISTING: layer(LISTING, listing if listing is not None else BASE, 1.0),
        OFFICIAL: layer(OFFICIAL, official if official is not None else BASE, 1.0),
    }


def finding(outcome, rule_id):
    return next(f for f in outcome.findings if f.rule_id == rule_id)


class TestClassificationPatterns:
    def test_all_agree_is_compliant(self):
        outcome = reconcile(three_layers())
        assert outcome.classification == Classification.COMPLIANT.value
        assert outcome.counts["failed"] == 0
        assert outcome.counts["review"] == 0

    def test_listing_is_the_outlier_means_seller_fraud(self):
        listing = {**BASE, "mrp": "Rs. 79.00"}
        outcome = reconcile(three_layers(listing=listing))
        assert outcome.classification == Classification.SELLER_FRAUD.value
        assert finding(outcome, "MRP-001").status == RuleStatus.FAIL.value
        assert finding(outcome, "MRP-003").status == RuleStatus.FAIL.value
        # Photo vs official still agree.
        assert finding(outcome, "MRP-002").status == RuleStatus.PASS.value

    def test_photo_and_listing_against_official_means_counterfeit(self):
        altered = {**BASE, "net_quantity": "450 g"}
        outcome = reconcile(three_layers(photo=altered, listing=altered))
        assert outcome.classification == Classification.COUNTERFEIT_OR_ILLEGAL_IMPORT.value

    def test_photo_alone_against_the_others_means_counterfeit(self):
        photo = {**BASE, "net_quantity": "450 g"}
        outcome = reconcile(three_layers(photo=photo))
        assert outcome.classification == Classification.COUNTERFEIT_OR_ILLEGAL_IMPORT.value

    def test_all_three_disagree_goes_to_review(self):
        outcome = reconcile(
            three_layers(
                photo={**BASE, "mrp": "Rs. 99"},
                listing={**BASE, "mrp": "Rs. 79"},
                official={**BASE, "mrp": "Rs. 129"},
            )
        )
        assert outcome.classification == Classification.MANUAL_REVIEW.value

    def test_seller_and_counterfeit_signals_together_go_to_review(self):
        outcome = reconcile(
            three_layers(
                photo={**BASE, "net_quantity": "450 g"},
                listing={**BASE, "mrp": "Rs. 79", "net_quantity": "450 g"},
            )
        )
        assert outcome.classification == Classification.MANUAL_REVIEW.value


class TestMissingSources:
    def test_missing_official_record_is_not_compliance(self):
        layers = three_layers()
        layers[OFFICIAL] = LayerData(
            OFFICIAL, available=False, reason="No registered declaration found."
        )
        outcome = reconcile(layers)
        assert outcome.classification == Classification.MANUAL_REVIEW.value
        assert "not evidence of compliance" in outcome.headline

    def test_missing_listing_is_not_compliance(self):
        layers = three_layers()
        layers[LISTING] = LayerData(LISTING, available=False, reason="Listing unavailable.")
        assert reconcile(layers).classification == Classification.MANUAL_REVIEW.value

    def test_unreadable_photo_is_not_compliance(self):
        layers = three_layers()
        layers[PHOTO] = LayerData(PHOTO, available=False, reason="OCR unavailable.")
        outcome = reconcile(layers)
        assert outcome.classification == Classification.MANUAL_REVIEW.value
        # Presence of mandatory declarations cannot be established, not failed.
        assert finding(outcome, "DECL-001").status == RuleStatus.REVIEW.value


class TestConfidence:
    def test_low_confidence_becomes_review_not_pass(self):
        outcome = reconcile(three_layers(photo_conf=0.40))
        assert outcome.classification == Classification.MANUAL_REVIEW.value
        assert finding(outcome, "MRP-001").status == RuleStatus.REVIEW.value

    def test_low_confidence_mismatch_does_not_become_a_failure(self):
        """A mismatch we are not sure we read correctly must not be a FAIL."""
        listing = {**BASE, "mrp": "Rs. 79.00"}
        outcome = reconcile(three_layers(listing=listing, photo_conf=0.66))
        assert finding(outcome, "MRP-001").status == RuleStatus.REVIEW.value

    def test_confidence_threshold_boundary(self):
        at_threshold = reconcile(three_layers(photo_conf=config.CONFIDENCE_THRESHOLD))
        assert finding(at_threshold, "DECL-001").status == RuleStatus.PASS.value

        below = reconcile(three_layers(photo_conf=config.CONFIDENCE_THRESHOLD - 0.01))
        assert finding(below, "DECL-001").status == RuleStatus.REVIEW.value


class TestPresenceRules:
    def test_missing_mandatory_declaration_fails(self):
        photo = {k: v for k, v in BASE.items() if k != "mrp"}
        outcome = reconcile(three_layers(photo=photo))
        assert finding(outcome, "DECL-001").status == RuleStatus.FAIL.value
        assert outcome.classification != Classification.COMPLIANT.value

    def test_any_of_group_is_satisfied_by_an_alternative(self):
        """Importer alone satisfies the manufacturer/packer/importer requirement."""
        photo = {k: v for k, v in BASE.items() if k != "manufacturer_name"}
        photo["importer_name"] = "Greyline Imports LLP"
        outcome = reconcile(
            {
                PHOTO: layer(PHOTO, photo),
                LISTING: layer(LISTING, photo, 1.0),
                OFFICIAL: layer(OFFICIAL, photo, 1.0),
            }
        )
        assert finding(outcome, "DECL-003").status == RuleStatus.PASS.value

    def test_unparseable_value_is_review_not_pass(self):
        photo = {**BASE, "mrp": "Rs. 4Z9.OO"}
        layers = three_layers(photo=photo)
        assert finding(reconcile(layers), "DECL-001").status == RuleStatus.REVIEW.value


class TestNotApplicable:
    def test_field_absent_everywhere_is_not_a_discrepancy(self):
        """A domestic product has no importer — that is N/A, not REVIEW."""
        outcome = reconcile(three_layers())
        for rule_id in ("IMP-001", "IMP-002", "IMP-003"):
            assert finding(outcome, rule_id).status == RuleStatus.NOT_APPLICABLE.value

    def test_field_on_one_side_only_is_review(self):
        listing = {k: v for k, v in BASE.items() if k != "mrp"}
        outcome = reconcile(three_layers(listing=listing))
        assert finding(outcome, "MRP-001").status == RuleStatus.REVIEW.value


class TestConsistencyRule:
    def test_expiry_after_manufacture_passes(self):
        photo = {**BASE, "expiry_date": "DEC 2026"}
        assert (
            finding(reconcile(three_layers(photo=photo)), "DATE-001").status
            == RuleStatus.PASS.value
        )

    def test_expiry_before_manufacture_fails(self):
        photo = {**BASE, "expiry_date": "DEC 2024"}
        assert (
            finding(reconcile(three_layers(photo=photo)), "DATE-001").status
            == RuleStatus.FAIL.value
        )

    def test_no_expiry_is_not_applicable(self):
        assert (
            finding(reconcile(three_layers()), "DATE-001").status
            == RuleStatus.NOT_APPLICABLE.value
        )


class TestFieldOutcomes:
    def test_equivalent_units_are_a_match_not_a_mismatch(self):
        outcome = reconcile(
            three_layers(photo={**BASE, "net_quantity": "1 kg"}, official={**BASE, "net_quantity": "1000 g"})
        )
        assert outcome.field_outcomes["net_quantity"].status == FieldStatus.MATCH.value

    def test_field_with_no_cross_rule_is_not_applicable(self):
        """The comparison table must not flag a field no rule compares."""
        outcome = reconcile(three_layers())
        assert outcome.field_outcomes["consumer_care"].status == FieldStatus.NOT_APPLICABLE.value


class TestDeterminism:
    def test_identical_input_produces_identical_output(self):
        first = reconcile(three_layers(listing={**BASE, "mrp": "Rs. 79"}))
        second = reconcile(three_layers(listing={**BASE, "mrp": "Rs. 79"}))
        assert first.classification == second.classification
        assert first.overall_confidence == second.overall_confidence
        assert [(f.rule_id, f.status) for f in first.findings] == [
            (f.rule_id, f.status) for f in second.findings
        ]

    def test_findings_are_ordered_worst_first(self):
        outcome = reconcile(three_layers(listing={**BASE, "mrp": "Rs. 79"}))
        rank = {"FAIL": 0, "REVIEW": 1, "PASS": 2, "NOT_APPLICABLE": 3}
        ranks = [rank[f.status] for f in outcome.findings]
        assert ranks == sorted(ranks)

    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
    def test_confidence_stays_in_range(self, confidence):
        outcome = reconcile(three_layers(photo_conf=confidence))
        assert 0.0 <= outcome.overall_confidence <= 1.0
