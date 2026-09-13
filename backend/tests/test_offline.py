"""
Offline guarantee (Build Manual sections 12 and 15).

The H18 checkpoint is "full demo run with network disabled". Rather than
trusting a rehearsal to catch a hidden dependency, this test physically breaks
outbound sockets and then drives the complete demo path. Any module that
quietly reaches for the network fails here instead of on stage.
"""

from __future__ import annotations

import socket

import pytest


class _NetworkDisabled(RuntimeError):
    pass


@pytest.fixture()
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise _NetworkDisabled("Outbound network access is disabled for this test.")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    yield


def test_seeded_cases_open_with_the_network_down(client, no_network):
    for case_id in ("TV-0001", "TV-0002", "TV-0003", "TV-0004"):
        body = client.get(f"/cases/{case_id}").json()
        assert body["classification"]
        assert body["findings"]


def test_evidence_and_crops_work_with_the_network_down(client, no_network):
    body = client.get("/cases/TV-0002").json()
    evidence_id = body["fields"]["mrp"]["photo"]["evidence_id"]

    assert client.get(f"/cases/TV-0002/evidence/{evidence_id}").status_code == 200
    assert client.get(f"/cases/TV-0002/evidence/{evidence_id}/crop").status_code == 200

    image = next(img for img in body["images"] if img["kind"] == "ORIGINAL")
    assert client.get(image["url"]).status_code == 200


def test_reports_generate_with_the_network_down(client, no_network):
    assert client.get("/cases/TV-0002/report").status_code == 200
    assert client.get("/cases/TV-0002/report", params={"format": "json"}).status_code == 200


def test_full_upload_path_works_with_the_network_down(client, no_network):
    from app.core import config

    image_bytes = (config.IMAGES_DIR / "TV-0002-himveda-oil.png").read_bytes()
    response = client.post(
        "/cases",
        files={"image": ("label.png", image_bytes, "image/png")},
        data={"identifier": "8907654321098"},
    )
    assert response.status_code == 201
    assert response.json()["classification"] == "SELLER_FRAUD"


def test_reverification_works_with_the_network_down(client, no_network):
    assert client.post("/cases/TV-0003/verify").json()["classification"] == (
        "COUNTERFEIT_OR_ILLEGAL_IMPORT"
    )


def test_history_and_search_work_with_the_network_down(client, no_network):
    assert client.get("/cases").json()["total"] >= 4
    assert client.get("/cases", params={"q": "himveda"}).json()["total"] >= 1


def test_health_reports_offline_ready(client, no_network):
    body = client.get("/health").json()
    assert body["offline_ready"] is True
    assert body["live_sources_enabled"] is False
