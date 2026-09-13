"""
Golden-case regression tests.

The cases used in the demo ARE the automated tests (Build Manual section 15),
so the demo data is a safety net rather than disposable mock content. Each runs
the complete path: PNG bytes → preprocessing → OCR → extraction →
normalization → source adapters → rules → classification.
"""

from __future__ import annotations

import pytest

from app.services.presenter import build_case_result
from app.services.case_service import get_case, verify_case
from app.engine.vocabulary import RuleStatus


def test_all_golden_cases_produce_the_expected_classification(seeded):
    mismatches = [(cid, exp, act) for cid, exp, act in seeded if exp != act]
    assert not mismatches, f"Golden-case classification drift: {mismatches}"


def test_every_golden_case_is_covered(seeded, golden_cases):
    assert len(seeded) == len(golden_cases) == 4
    classifications = {actual for _, _, actual in seeded}
    assert classifications == {
        "COMPLIANT",
        "SELLER_FRAUD",
        "COUNTERFEIT_OR_ILLEGAL_IMPORT",
        "MANUAL_REVIEW",
    }


class TestCompliantCase:
    def test_no_failures_and_full_evidence(self, client):
        result = client.get("/cases/TV-0001").json()
        assert result["classification"] == "COMPLIANT"
        assert result["summary"]["failed"] == 0
        assert result["summary"]["review"] == 0
        assert result["summary"]["fields_mismatched"] == 0
        assert all(source["available"] for source in result["sources"].values())


class TestSellerFraudCase:
    def test_mrp_is_the_only_mismatch(self, client):
        result = client.get("/cases/TV-0002").json()
        assert result["classification"] == "SELLER_FRAUD"
        assert result["fields"]["mrp"]["status"] == "MISMATCH"
        assert result["summary"]["fields_mismatched"] == 1

    def test_photo_and_official_agree_listing_differs(self, client):
        mrp = client.get("/cases/TV-0002").json()["fields"]["mrp"]
        assert mrp["photo"]["norm"]["amount"] == 249.0
        assert mrp["official"]["norm"]["amount"] == 249.0
        assert mrp["listing"]["norm"]["amount"] == 199.0

    def test_the_deciding_rules_failed(self, client):
        findings = {f["rule_id"]: f for f in client.get("/cases/TV-0002").json()["findings"]}
        assert findings["MRP-001"]["status"] == RuleStatus.FAIL.value
        assert findings["MRP-003"]["status"] == RuleStatus.FAIL.value
        assert findings["MRP-002"]["status"] == RuleStatus.PASS.value

    def test_every_failure_carries_evidence(self, client):
        result = client.get("/cases/TV-0002").json()
        for finding in result["findings"]:
            if finding["status"] == RuleStatus.FAIL.value:
                assert finding["evidence_ids"], f"{finding['rule_id']} has no evidence"


class TestCounterfeitCase:
    def test_product_conflicts_with_the_registry(self, client):
        result = client.get("/cases/TV-0003").json()
        assert result["classification"] == "COUNTERFEIT_OR_ILLEGAL_IMPORT"
        assert result["fields"]["net_quantity"]["status"] == "MISMATCH"
        assert result["fields"]["importer_name"]["status"] == "MISMATCH"

    def test_quantities_are_compared_in_base_units(self, client):
        quantity = client.get("/cases/TV-0003").json()["fields"]["net_quantity"]
        assert quantity["photo"]["norm"]["value"] == 450.0
        assert quantity["official"]["norm"]["value"] == 500.0


class TestInsufficientEvidenceCase:
    def test_official_record_is_missing_and_declared_so(self, client):
        result = client.get("/cases/TV-0004").json()
        assert result["classification"] == "MANUAL_REVIEW"
        assert result["sources"]["OFFICIAL"]["available"] is False
        assert result["sources"]["OFFICIAL"]["note"]

    def test_low_confidence_mrp_is_never_accepted(self, client):
        result = client.get("/cases/TV-0004").json()
        assert result["fields"]["mrp"]["photo"]["confidence"] < 0.65
        assert result["fields"]["mrp"]["status"] == "INSUFFICIENT"

        findings = {f["rule_id"]: f for f in result["findings"]}
        assert findings["DECL-001"]["status"] == RuleStatus.REVIEW.value

    def test_nothing_is_reported_as_a_confident_failure(self, client):
        result = client.get("/cases/TV-0004").json()
        assert result["summary"]["failed"] == 0
        assert result["summary"]["review"] > 0


class TestReverificationIsStable:
    @pytest.mark.parametrize("case_id", ["TV-0001", "TV-0002", "TV-0003", "TV-0004"])
    def test_rerunning_verification_changes_nothing(self, client, case_id):
        before = client.get(f"/cases/{case_id}").json()
        after = client.post(f"/cases/{case_id}/verify").json()

        assert before["classification"] == after["classification"]
        assert before["overall_confidence"] == after["overall_confidence"]
        assert before["headline"] == after["headline"]
        assert [(f["rule_id"], f["status"]) for f in before["findings"]] == [
            (f["rule_id"], f["status"]) for f in after["findings"]
        ]

    @pytest.mark.parametrize("case_id", ["TV-0001", "TV-0002", "TV-0003", "TV-0004"])
    def test_evidence_ids_are_stable_across_reruns(self, session, case_id):
        """Evidence ids must not churn, or saved report references would rot."""
        case = get_case(session, case_id)
        first = sorted(e.evidence_id for e in build_case_result(session, case).evidence)
        verify_case(session, case)
        session.refresh(case)
        second = sorted(e.evidence_id for e in build_case_result(session, case).evidence)
        assert first == second
