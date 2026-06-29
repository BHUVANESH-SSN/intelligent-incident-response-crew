import os
import sys
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.parsers.pagerduty import parse_pagerduty_alert
from fastapi.testclient import TestClient


def _pd_payload(urgency="high", title="High memory usage", service_name="payment-api", details="Memory at 95%"):
    return {
        "event": {
            "id": "01BAGNKMPNHAX",
            "event_type": "incident.triggered",
            "occurred_at": "2026-06-29T10:00:00Z",
            "data": {
                "id": "Q14CSQER",
                "type": "incident",
                "status": "triggered",
                "title": title,
                "urgency": urgency,
                "service": {"id": "SVC1", "name": service_name},
                "body": {"type": "incident_body", "details": details},
            }
        }
    }


def test_high_urgency_maps_to_p1():
    result = parse_pagerduty_alert(_pd_payload(urgency="high"))
    assert result["severity"] == "P1"


def test_low_urgency_maps_to_p3():
    result = parse_pagerduty_alert(_pd_payload(urgency="low"))
    assert result["severity"] == "P3"


def test_unknown_urgency_maps_to_p2():
    result = parse_pagerduty_alert(_pd_payload(urgency="warning"))
    assert result["severity"] == "P2"


def test_service_name_extracted():
    result = parse_pagerduty_alert(_pd_payload(service_name="auth-service"))
    assert result["service"] == "auth-service"


def test_description_combines_title_and_details():
    result = parse_pagerduty_alert(_pd_payload(title="Memory spike", details="95% usage"))
    assert "Memory spike" in result["description"]
    assert "95% usage" in result["description"]


def test_alert_type_is_pagerduty():
    result = parse_pagerduty_alert(_pd_payload())
    assert result["alert_type"] == "pagerduty"


def test_alert_id_from_incident_id():
    result = parse_pagerduty_alert(_pd_payload())
    assert result["alert_id"] == "Q14CSQER"


def test_required_fields_present():
    result = parse_pagerduty_alert(_pd_payload())
    for field in ["service", "severity", "description", "alert_type", "alert_id"]:
        assert field in result, f"Missing field: {field}"


def test_empty_body_details_handled():
    payload = _pd_payload()
    payload["event"]["data"]["body"] = {}
    result = parse_pagerduty_alert(payload)
    assert "description" in result
    assert len(result["description"]) > 0


def test_missing_event_key_raises():
    with pytest.raises((KeyError, ValueError)):
        parse_pagerduty_alert({"not_event": {}})


@pytest.fixture
def client():
    from examples.webhook_server import app
    return TestClient(app)


def test_pagerduty_webhook_accepts_valid_payload(client):
    from unittest.mock import patch
    from src.orchestrator import orchestrator
    with patch.object(orchestrator, "process_alert", return_value={"status": "completed"}):
        resp = client.post("/webhook/pagerduty", json=_pd_payload())
    assert resp.status_code == 202
    assert "incident_id" in resp.json()


def test_pagerduty_webhook_rejects_bad_json(client):
    resp = client.post(
        "/webhook/pagerduty",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_pagerduty_webhook_rejects_missing_event_key(client):
    resp = client.post("/webhook/pagerduty", json={"wrong": "payload"})
    assert resp.status_code == 400
