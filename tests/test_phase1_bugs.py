"""Regression tests for the three Phase-1 bug fixes."""

import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from examples.webhook_server import app
from src.orchestrator import orchestrator, IncidentResponseOrchestrator


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_singleton():
    orchestrator.pending_incidents.clear()
    orchestrator.resolved_incidents.clear()
    yield
    orchestrator.pending_incidents.clear()
    orchestrator.resolved_incidents.clear()


ALERT = {
    "service": "payment-api",
    "alert_type": "high_error_rate",
    "severity": "P3",
    "description": "Error rate elevated",
    "metric_value": 0.25,
    "threshold": 0.10,
}


# ── Bug 1: incident_id passed through ────────────────────────────────────────

def test_returned_incident_id_matches_orchestrator_key(client):
    """The incident_id the caller receives must be the same key stored in
    orchestrator.resolved_incidents after the background task runs."""
    captured = {}

    def fake_process(payload, incident_id=None):
        captured["used_id"] = incident_id
        return {"status": "completed"}

    with patch.object(orchestrator, "process_alert", side_effect=fake_process):
        resp = client.post("/webhook/alert", json=ALERT)

    assert resp.status_code == 202
    returned_id = resp.json()["incident_id"]
    assert returned_id == captured["used_id"], (
        f"Caller got {returned_id!r} but orchestrator used {captured['used_id']!r}"
    )


def test_orchestrator_accepts_incident_id_kwarg():
    """process_alert must accept an explicit incident_id and use it as the key."""
    orch = IncidentResponseOrchestrator()
    payload = {
        "service": "svc",
        "severity": "P3",
        "description": "test",
        "alert_type": "generic",
    }
    fake_crew = MagicMock()
    fake_crew.kickoff.return_value = '{"root_cause": "x", "confidence": 0.8}'
    with patch("src.orchestrator.create_incident_response_crew", return_value=fake_crew):
        result = orch.process_alert(payload, incident_id="my-fixed-id")

    assert result["incident_id"] == "my-fixed-id"
    assert "my-fixed-id" in orch.resolved_incidents


# ── Bug 2: body read once ─────────────────────────────────────────────────────

def test_webhook_sig_verifier_is_sync_and_takes_raw_bytes():
    """_verify_webhook_sig must be importable, synchronous, and accept bytes."""
    import inspect
    from examples.webhook_server import _verify_webhook_sig
    assert not inspect.iscoroutinefunction(_verify_webhook_sig), (
        "_verify_webhook_sig must be a plain sync function, not async"
    )
    # No WEBHOOK_SECRET set → should return None without raising.
    result = _verify_webhook_sig(b'{"key": "value"}', {})
    assert result is None


def test_webhook_sig_rejects_bad_signature(monkeypatch):
    """A wrong HMAC signature must raise 403."""
    import os
    from fastapi import HTTPException
    from examples.webhook_server import _verify_webhook_sig
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    with pytest.raises(HTTPException) as exc_info:
        _verify_webhook_sig(b'{"key":"value"}', {"X-Webhook-Signature": "sha256=badhash"})
    assert exc_info.value.status_code == 403
