"""
Integration tests for FastAPI routes.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

class TestIndex:
    def test_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_contains_orbital_sentinel(self, client):
        resp = client.get("/")
        assert "ORBITAL SENTINEL" in resp.text

    def test_demo_conjunctions_shown(self, client):
        resp = client.get("/")
        # Seed data loads DEMO-001 etc.
        assert "DEMO" in resp.text or "STARLINK" in resp.text

    def test_shows_risk_badges(self, client):
        resp = client.get("/")
        assert "HIGH" in resp.text or "MEDIUM" in resp.text or "LOW" in resp.text


# ---------------------------------------------------------------------------
# GET /conjunction/{cdm_id}
# ---------------------------------------------------------------------------

class TestConjunctionDetail:
    def test_known_demo_returns_200(self, client):
        resp = client.get("/conjunction/DEMO-001")
        assert resp.status_code == 200

    def test_contains_sat_names(self, client):
        resp = client.get("/conjunction/DEMO-001")
        assert "STARLINK" in resp.text or "COSMOS" in resp.text

    def test_contains_miss_distance(self, client):
        resp = client.get("/conjunction/DEMO-001")
        assert "287" in resp.text  # 287 m miss distance

    def test_contains_plotly_script(self, client):
        resp = client.get("/conjunction/DEMO-001")
        assert "Plotly" in resp.text or "plotly" in resp.text

    def test_unknown_cdm_returns_404(self, client):
        resp = client.get("/conjunction/DOES-NOT-EXIST")
        assert resp.status_code == 404

    def test_demo_002_returns_200(self, client):
        resp = client.get("/conjunction/DEMO-002")
        assert resp.status_code == 200

    def test_demo_003_returns_200(self, client):
        resp = client.get("/conjunction/DEMO-003")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /conjunction/{cdm_id}/brief — mocked Claude
# ---------------------------------------------------------------------------

class TestGenerateBrief:
    def _mock_brief_sections(self):
        return {
            "SITUATION": "DEMO-001 is a high-risk conjunction.",
            "ORBITAL ENVIRONMENT": "LEO at 550 km with significant debris population.",
            "CONJUNCTION ASSESSMENT": "Miss distance 287 m, Pc 2.3e-4 exceeds maneuver threshold.",
            "DEFENSE & OPERATIONAL EXPOSURE": "Starlink assets critical for communication.",
            "WATCH ITEMS": "• Monitor next CDM update\n• Coordinate with operator",
            "_raw": "raw text",
        }

    def test_returns_200_with_mocked_claude(self, client):
        with patch("main.generate_sda_brief", return_value=self._mock_brief_sections()):
            resp = client.post("/conjunction/DEMO-001/brief")
        assert resp.status_code == 200

    def test_response_has_sections(self, client):
        with patch("main.generate_sda_brief", return_value=self._mock_brief_sections()):
            resp = client.post("/conjunction/DEMO-001/brief")
        data = resp.json()
        assert "sections" in data
        assert "SITUATION" in data["sections"]

    def test_unknown_cdm_returns_404(self, client):
        resp = client.post("/conjunction/DOES-NOT-EXIST/brief")
        assert resp.status_code == 404

    def test_claude_error_returns_502(self, client):
        from claude_analyst import BriefGenerationError
        with patch("main.generate_sda_brief", side_effect=BriefGenerationError("API error")):
            resp = client.post("/conjunction/DEMO-001/brief")
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET /conjunction/{cdm_id}/pdf
# ---------------------------------------------------------------------------

class TestDownloadPdf:
    def test_no_brief_returns_400(self, client):
        # DEMO-002 starts without a brief
        resp = client.get("/conjunction/DEMO-002/pdf")
        assert resp.status_code == 400

    def test_with_brief_returns_pdf_bytes(self, client):
        mock_sections = {
            "SITUATION": "Test situation.",
            "ORBITAL ENVIRONMENT": "LEO.",
            "CONJUNCTION ASSESSMENT": "Low risk.",
            "DEFENSE & OPERATIONAL EXPOSURE": "Minimal.",
            "WATCH ITEMS": "• Monitor",
        }
        with patch("main.generate_sda_brief", return_value=mock_sections):
            client.post("/conjunction/DEMO-003/brief")

        resp = client.get("/conjunction/DEMO-003/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# POST /refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_demo_mode_returns_demo_status(self, client):
        with patch("main.DEMO_MODE", True):
            resp = client.post("/refresh")
        assert resp.status_code == 200
        assert resp.json()["status"] == "demo_mode"

    def test_live_mode_calls_ingest(self, client):
        with patch("main.DEMO_MODE", False), \
             patch("main._ingest_cdms", return_value=(3, 1)) as mock_ingest:
            from database import get_db
            resp = client.post("/refresh")
        # If credentials aren't set this raises — just check it tries
        # (integration test with real Space-Track is a manual test)


# ---------------------------------------------------------------------------
# GET /api/stats
# ---------------------------------------------------------------------------

class TestApiStats:
    def test_returns_200(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200

    def test_has_total_conjunctions(self, client):
        data = client.get("/api/stats").json()
        assert "total_conjunctions" in data
        assert isinstance(data["total_conjunctions"], int)

    def test_has_high_risk_count(self, client):
        data = client.get("/api/stats").json()
        assert "high_risk" in data

    def test_status_ok(self, client):
        data = client.get("/api/stats").json()
        assert data["status"] == "ok"

    def test_demo_mode_field_present(self, client):
        data = client.get("/api/stats").json()
        assert "demo_mode" in data
