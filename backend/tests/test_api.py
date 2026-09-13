"""API contract tests — every endpoint from Build Manual section 5."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core import config


@pytest.fixture(scope="module")
def demo_image_bytes():
    path = config.IMAGES_DIR / "TV-0001-sunrise-atta.png"
    return path.read_bytes()


class TestHealth:
    def test_reports_ready(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["database_ok"] is True
        assert body["golden_cases"] == 4
        assert body["live_sources_enabled"] is False
        assert body["offline_ready"] is True


class TestCaseList:
    def test_lists_all_cases(self, client):
        body = client.get("/cases").json()
        assert body["total"] >= 4
        assert {item["case_id"] for item in body["items"]} >= {
            "TV-0001",
            "TV-0002",
            "TV-0003",
            "TV-0004",
        }

    def test_search_by_product(self, client):
        body = client.get("/cases", params={"q": "alpina"}).json()
        assert body["total"] == 1
        assert body["items"][0]["case_id"] == "TV-0003"

    def test_search_by_identifier(self, client):
        body = client.get("/cases", params={"q": "8907654321098"}).json()
        assert body["items"][0]["case_id"] == "TV-0002"

    def test_filter_by_classification(self, client):
        body = client.get("/cases", params={"classification": "SELLER_FRAUD"}).json()
        assert all(item["classification"] == "SELLER_FRAUD" for item in body["items"])

    def test_unknown_search_returns_empty_not_error(self, client):
        body = client.get("/cases", params={"q": "zzzznothing"}).json()
        assert body["total"] == 0
        assert body["items"] == []


class TestCaseResultShape:
    """The frozen contract the frontend is written against."""

    def test_top_level_keys(self, client):
        body = client.get("/cases/TV-0002").json()
        for key in (
            "case_id",
            "classification",
            "overall_confidence",
            "headline",
            "product",
            "sources",
            "images",
            "fields",
            "field_order",
            "findings",
            "evidence",
            "summary",
            "disclaimer",
        ):
            assert key in body, f"missing contract key: {key}"

    def test_each_field_has_three_layers_and_a_status(self, client):
        body = client.get("/cases/TV-0002").json()
        assert body["field_order"]
        for name in body["field_order"]:
            field = body["fields"][name]
            assert {"photo", "listing", "official"} <= set(field)
            assert field["status"] in {
                "MATCH",
                "MISMATCH",
                "REVIEW",
                "INSUFFICIENT",
                "NOT_APPLICABLE",
            }

    def test_findings_carry_rule_severity_and_explanation(self, client):
        for finding in client.get("/cases/TV-0002").json()["findings"]:
            assert finding["rule_id"]
            assert finding["severity"] in {"HIGH", "MEDIUM", "LOW", "INFO"}
            assert finding["status"] in {"PASS", "FAIL", "REVIEW", "NOT_APPLICABLE"}
            assert finding["explanation"].strip()

    def test_evidence_ids_referenced_by_findings_all_exist(self, client):
        body = client.get("/cases/TV-0002").json()
        known = {item["evidence_id"] for item in body["evidence"]}
        for finding in body["findings"]:
            for evidence_id in finding["evidence_ids"]:
                assert evidence_id in known, f"dangling evidence ref {evidence_id}"

    def test_missing_case_returns_404(self, client):
        assert client.get("/cases/TV-9999").status_code == 404


class TestEvidenceEndpoints:
    def test_evidence_detail(self, client):
        body = client.get("/cases/TV-0002").json()
        evidence_id = body["fields"]["mrp"]["photo"]["evidence_id"]
        detail = client.get(f"/cases/TV-0002/evidence/{evidence_id}").json()
        assert detail["source_type"] == "PHOTO"
        assert detail["field_name"] == "mrp"
        assert detail["bbox"]
        assert detail["has_crop"] is True

    def test_crop_returns_a_png(self, client):
        body = client.get("/cases/TV-0002").json()
        evidence_id = body["fields"]["mrp"]["photo"]["evidence_id"]
        response = client.get(f"/cases/TV-0002/evidence/{evidence_id}/crop")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        with Image.open(io.BytesIO(response.content)) as crop:
            assert crop.width > 0 and crop.height > 0

    def test_text_source_evidence_has_no_crop(self, client):
        body = client.get("/cases/TV-0002").json()
        evidence_id = body["fields"]["mrp"]["listing"]["evidence_id"]
        assert client.get(f"/cases/TV-0002/evidence/{evidence_id}/crop").status_code == 404

    def test_listing_evidence_exposes_the_raw_payload(self, client):
        body = client.get("/cases/TV-0002").json()
        evidence_id = body["fields"]["mrp"]["listing"]["evidence_id"]
        detail = client.get(f"/cases/TV-0002/evidence/{evidence_id}").json()
        assert detail["metadata"]["raw_snapshot"]["listing_id"]

    def test_unknown_evidence_returns_404(self, client):
        assert client.get("/cases/TV-0002/evidence/EV-XXXX-99").status_code == 404


class TestImages:
    def test_original_image_is_served_from_the_database(self, client):
        body = client.get("/cases/TV-0002").json()
        image = next(img for img in body["images"] if img["kind"] == "ORIGINAL")
        response = client.get(image["url"])
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"

    def test_unknown_image_returns_404(self, client):
        assert client.get("/cases/TV-0002/images/IMG-NOPE").status_code == 404


class TestReports:
    def test_html_report_contains_the_verdict_and_evidence(self, client):
        response = client.get("/cases/TV-0002/report")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        body = response.text
        assert "Seller-side discrepancy".upper() in body.upper()
        assert "MRP-001" in body
        assert "249" in body and "199" in body

    def test_json_report_matches_the_case_result(self, client):
        report = client.get("/cases/TV-0002/report", params={"format": "json"}).json()
        case = client.get("/cases/TV-0002").json()
        assert report["classification"] == case["classification"]
        assert report["headline"] == case["headline"]

    def test_pdf_report(self, client):
        response = client.get("/cases/TV-0002/report", params={"format": "pdf"})
        # 503 is the documented degradation when reportlab is absent.
        assert response.status_code in {200, 503}
        if response.status_code == 200:
            assert response.content.startswith(b"%PDF")

    def test_invalid_format_is_rejected(self, client):
        assert client.get("/cases/TV-0002/report", params={"format": "docx"}).status_code == 422

    def test_report_for_unknown_case_is_404(self, client):
        assert client.get("/cases/TV-9999/report").status_code == 404


class TestCaseCreation:
    def test_upload_creates_a_verified_case(self, client, demo_image_bytes):
        response = client.post(
            "/cases",
            files={"image": ("label.png", demo_image_bytes, "image/png")},
            data={"identifier": "8901234567890"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["case_id"].startswith("TV-")
        assert body["classification"] == "COMPLIANT"

    def test_unknown_identifier_routes_to_review(self, client, demo_image_bytes):
        response = client.post(
            "/cases",
            files={"image": ("label.png", demo_image_bytes, "image/png")},
            data={"identifier": "0000000000000"},
        )
        assert response.status_code == 201
        body = client.get(f"/cases/{response.json()['case_id']}").json()
        assert body["classification"] == "MANUAL_REVIEW"
        assert body["sources"]["OFFICIAL"]["available"] is False
        assert body["sources"]["LISTING"]["available"] is False

    def test_unreadable_image_routes_to_review_rather_than_crashing(self, client):
        """No OCR fixture and no Tesseract must degrade, not explode."""
        buffer = io.BytesIO()
        Image.new("RGB", (600, 400), (235, 235, 230)).save(buffer, format="PNG")
        response = client.post(
            "/cases",
            files={"image": ("blank.png", buffer.getvalue(), "image/png")},
            data={"identifier": "8901234567890"},
        )
        assert response.status_code == 201
        body = client.get(f"/cases/{response.json()['case_id']}").json()
        assert body["classification"] == "MANUAL_REVIEW"
        assert body["sources"]["PHOTO"]["available"] is False

    def test_corrupt_upload_is_rejected(self, client):
        response = client.post(
            "/cases",
            files={"image": ("bad.png", b"definitely not an image", "image/png")},
            data={"identifier": "8901234567890"},
        )
        assert response.status_code == 422

    def test_missing_identifier_is_rejected(self, client, demo_image_bytes):
        response = client.post(
            "/cases",
            files={"image": ("label.png", demo_image_bytes, "image/png")},
            data={"identifier": "   "},
        )
        assert response.status_code == 422

    def test_unsupported_content_type_is_rejected(self, client, demo_image_bytes):
        response = client.post(
            "/cases",
            files={"image": ("label.pdf", demo_image_bytes, "application/pdf")},
            data={"identifier": "8901234567890"},
        )
        assert response.status_code == 415


class TestOpsEndpoints:
    def test_rules_are_introspectable(self, client):
        body = client.get("/rules").json()
        assert body["ruleset_version"]
        assert len(body["rules"]) >= 20
        ids = {rule["rule_id"] for rule in body["rules"]}
        assert {"MRP-001", "MRP-002", "MRP-003", "DECL-001"} <= ids

    def test_classifications_are_documented(self, client):
        codes = {item["code"] for item in client.get("/classifications").json()["classifications"]}
        assert codes == {
            "COMPLIANT",
            "SELLER_FRAUD",
            "COUNTERFEIT_OR_ILLEGAL_IMPORT",
            "MANUAL_REVIEW",
        }
