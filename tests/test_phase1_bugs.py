"""Regression tests for the three Phase-1 bug fixes."""

import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from examples.webhook_server import app
from src.orchestrator import orchestrator, IncidentResponseOrchestrator
from src.db import init_db, SessionLocal
from src.models.db_models import IncidentRecord


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_singleton():
    init_db()
    orchestrator.pending_incidents.clear()
    with SessionLocal() as session:
        session.query(IncidentRecord).delete()
        session.commit()
    yield
    orchestrator.pending_incidents.clear()
    with SessionLocal() as session:
        session.query(IncidentRecord).delete()
        session.commit()


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
    assert orch.get_incident("my-fixed-id")["status"] != "not_found"


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


# ── Bug 3: __main__ import path ───────────────────────────────────────────────

def test_main_block_uses_app_object_not_string():
    """The __main__ block must not pass a bare string 'webhook_server:app'
    to uvicorn.run — it should pass the app object directly."""
    import ast, pathlib
    src = (pathlib.Path(__file__).parent.parent / "examples/webhook_server.py").read_text()
    tree = ast.parse(src)

    # Find the if __name__ == "__main__": block
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
            ):
                # Stringify the body and check for the bad string
                body_src = ast.unparse(node)
                assert "webhook_server:app" not in body_src, (
                    "__main__ block still uses bare 'webhook_server:app' string — "
                    "use uvicorn.run(app, ...) instead"
                )


# ── Task 4: bearer-token auth on read endpoints ───────────────────────────────

def test_incidents_rejects_when_api_token_set(client, monkeypatch):
    """GET /incidents must return 401 when API_TOKEN is configured but header absent."""
    monkeypatch.setenv("API_TOKEN", "secret-token")
    resp = client.get("/incidents")
    assert resp.status_code == 401


def test_incidents_accepts_correct_token(client, monkeypatch):
    """GET /incidents must return 200 when the correct Bearer token is provided."""
    monkeypatch.setenv("API_TOKEN", "secret-token")
    resp = client.get("/incidents", headers={"Authorization": "Bearer secret-token"})
    assert resp.status_code == 200


def test_incidents_rejects_wrong_token(client, monkeypatch):
    """GET /incidents must return 403 when a wrong token is provided."""
    monkeypatch.setenv("API_TOKEN", "secret-token")
    resp = client.get("/incidents", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 403


def test_health_does_not_require_token(client, monkeypatch):
    """GET /health must remain open — no token required."""
    monkeypatch.setenv("API_TOKEN", "secret-token")
    resp = client.get("/health")
    assert resp.status_code == 200


def test_incident_detail_rejects_without_token(client, monkeypatch):
    """GET /incident/{id} must return 401 when API_TOKEN is set and header absent."""
    monkeypatch.setenv("API_TOKEN", "secret-token")
    resp = client.get("/incident/nonexistent-id")
    assert resp.status_code == 401


# ── Task 5: crewai version pin ────────────────────────────────────────────────

def test_crewai_version_pinned_in_requirements():
    """requirements.txt must pin crewai to a <0.30.0 upper bound."""
    import pathlib
    reqs = (pathlib.Path(__file__).parent.parent / "requirements.txt").read_text()
    crewai_lines = [l for l in reqs.splitlines() if l.startswith("crewai>=")]
    assert crewai_lines, "crewai must start with crewai>= in requirements.txt"
    assert any("<0.30.0" in l for l in crewai_lines), (
        f"crewai line must contain <0.30.0 upper bound, got: {crewai_lines}"
    )


# ── Task 4: /metrics auth ──────────────────────────────────────────────────────

def test_metrics_rejects_without_token(client, monkeypatch):
    """GET /metrics must return 401 when API_TOKEN is set and header absent."""
    monkeypatch.setenv("API_TOKEN", "secret-token")
    resp = client.get("/metrics")
    assert resp.status_code == 401


def test_metrics_accepts_correct_token(client, monkeypatch):
    """GET /metrics must return 200 when the correct Bearer token is provided."""
    monkeypatch.setenv("API_TOKEN", "secret-token")
    resp = client.get("/metrics", headers={"Authorization": "Bearer secret-token"})
    assert resp.status_code == 200


# ── Escalation logic (_evaluate_escalation) ───────────────────────────────────

@pytest.fixture
def orch_instance():
    from src.orchestrator import IncidentResponseOrchestrator
    return IncidentResponseOrchestrator()


@pytest.fixture
def p1_alert():
    from src.models.incident import Alert, SeverityLevel
    return Alert(
        alert_id="esc-1",
        service="payment-api",
        alert_type="high_error_rate",
        severity=SeverityLevel.P1,
        description="Critical error",
        metric_value=0.9,
        threshold=0.10,
    )


@pytest.fixture
def p3_alert():
    from src.models.incident import Alert, SeverityLevel
    return Alert(
        alert_id="esc-2",
        service="payment-api",
        alert_type="high_error_rate",
        severity=SeverityLevel.P3,
        description="Minor error",
        metric_value=0.15,
        threshold=0.10,
    )


def test_escalation_on_low_confidence(orch_instance, p3_alert):
    """Confidence below MIN_CONFIDENCE_FOR_AUTO_FIX triggers escalation."""
    summary = orch_instance._process_crew_result(
        "inc-low", p3_alert, '{"root_cause": "x", "confidence": 0.4}', 1.0
    )
    assert summary.escalated is True
    assert "confidence" in summary.escalation_reason.lower()


def test_no_escalation_on_high_confidence(orch_instance, p3_alert):
    """Confidence above threshold with fast duration and non-P1 should not escalate."""
    summary = orch_instance._process_crew_result(
        "inc-high", p3_alert, '{"root_cause": "x", "confidence": 0.9}', 1.0
    )
    assert summary.escalated is False


def test_escalation_on_p1_severity(orch_instance, p1_alert):
    """P1 severity always escalates regardless of confidence."""
    summary = orch_instance._process_crew_result(
        "inc-p1", p1_alert, '{"root_cause": "x", "confidence": 0.95}', 1.0
    )
    assert summary.escalated is True
    assert "p1" in summary.escalation_reason.lower()


def test_process_alert_status_reflects_escalation(client, monkeypatch):
    """process_alert must return status='escalated' when summary escalates."""
    from unittest.mock import patch, MagicMock
    from src.orchestrator import orchestrator

    fake_crew = MagicMock()
    fake_crew.kickoff.return_value = '{"root_cause": "x", "confidence": 0.3}'
    payload = {
        "service": "svc",
        "alert_type": "generic",
        "severity": "P3",
        "description": "Low confidence test",
        "metric_value": 0.2,
        "threshold": 0.1,
    }
    with patch("src.orchestrator.create_incident_response_crew", return_value=fake_crew):
        result = orchestrator.process_alert(payload)

    assert result["status"] == "escalated"
