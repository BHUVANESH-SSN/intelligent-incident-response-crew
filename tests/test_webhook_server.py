"""Tests for the FastAPI webhook endpoints.

Hermetic: orchestrator.process_alert is patched so no crew/LLM runs. The
endpoint dispatches via BackgroundTasks; TestClient runs those tasks after
the response, against the patched method.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from examples.webhook_server import app
from src.orchestrator import orchestrator


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_singleton():
    """Avoid cross-test pollution of the module-level orchestrator singleton."""
    from src.db import init_db, SessionLocal
    from src.models.db_models import IncidentRecord
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


def test_post_alert_valid_returns_202_with_incident_id(client):
    body = {
        "service": "payment-api",
        "alert_type": "high_error_rate",
        "severity": "P1",
        "description": "Error rate 45%",
        "metric_value": 0.45,
        "threshold": 0.10,
    }
    # Patch the singleton method so the background task does not run a crew.
    with patch.object(
        orchestrator, "process_alert", return_value={"status": "completed"}
    ) as mk:
        resp = client.post("/webhook/alert", json=body)

    assert resp.status_code == 202
    payload = resp.json()
    assert "incident_id" in payload
    assert payload["status"] == "received"
    # Background task ran with the patched, crew-free method.
    assert mk.called


def test_post_alert_missing_fields_returns_400(client):
    resp = client.post("/webhook/alert", json={"service": "only-service"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "severity" in detail and "description" in detail


def test_health_returns_200_healthy(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "pending_incidents" in data
    assert "resolved_incidents" in data


def test_incidents_returns_pending_resolved_structure(client):
    resp = client.get("/incidents")
    assert resp.status_code == 200
    data = resp.json()
    assert set(["pending", "resolved", "total_pending", "total_resolved"]) <= set(
        data.keys()
    )
    assert data["total_pending"] == 0
    assert data["total_resolved"] == 0
