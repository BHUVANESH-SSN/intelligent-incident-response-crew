import os
import sys
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------- fingerprint tests ----------

def test_same_alert_same_hour_gives_same_fingerprint():
    from src.dedup import compute_fingerprint
    payload = {"service": "payment-api", "alert_type": "high_error_rate", "severity": "P1"}
    fp1 = compute_fingerprint(payload)
    fp2 = compute_fingerprint(payload)
    assert fp1 == fp2


def test_different_services_give_different_fingerprints():
    from src.dedup import compute_fingerprint
    fp1 = compute_fingerprint({"service": "svc-a", "alert_type": "x", "severity": "P1"})
    fp2 = compute_fingerprint({"service": "svc-b", "alert_type": "x", "severity": "P1"})
    assert fp1 != fp2


# ---------- RedisDeduplicator mock-mode tests ----------

def _make_dedup_mock_mode():
    from src.integrations.redis_client import RedisDeduplicator
    d = object.__new__(RedisDeduplicator)
    d._available = False
    d._mock_store = {}
    return d


def test_check_returns_none_for_unknown():
    dedup = _make_dedup_mock_mode()
    assert dedup.check("unknown-fp") is None


def test_set_and_check_roundtrip():
    dedup = _make_dedup_mock_mode()
    dedup.set("fp-abc", "incident-123")
    assert dedup.check("fp-abc") == "incident-123"


def test_set_overwrites_existing():
    dedup = _make_dedup_mock_mode()
    dedup.set("fp-abc", "incident-old")
    dedup.set("fp-abc", "incident-new")
    assert dedup.check("fp-abc") == "incident-new"


# ---------- webhook dedup integration test ----------

def test_duplicate_alert_returns_existing_incident_id():
    """Second identical alert within the same hour returns the first incident_id."""
    from examples.webhook_server import app
    from src.orchestrator import orchestrator
    from unittest.mock import patch
    from fastapi.testclient import TestClient

    orchestrator.pending_incidents.clear()
    client = TestClient(app)
    alert = {
        "service": "payment-api",
        "alert_type": "high_error_rate",
        "severity": "P1",
        "description": "Error rate spike",
    }

    mock_dedup = _make_dedup_mock_mode()

    with patch("examples.webhook_server.deduplicator", mock_dedup):
        resp1 = client.post("/webhook/alert", json=alert)
        assert resp1.status_code == 202
        incident_id_1 = resp1.json()["incident_id"]

        resp2 = client.post("/webhook/alert", json=alert)
        assert resp2.status_code == 200
        assert resp2.json()["incident_id"] == incident_id_1
        assert resp2.json()["status"] == "deduplicated"
