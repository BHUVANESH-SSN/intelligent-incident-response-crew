import os
import json
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import init_db, SessionLocal
from src.models.db_models import IncidentRecord
from src.orchestrator import IncidentResponseOrchestrator


@pytest.fixture(autouse=True)
def fresh_db():
    init_db()
    with SessionLocal() as session:
        session.query(IncidentRecord).delete()
        session.commit()
    yield
    with SessionLocal() as session:
        session.query(IncidentRecord).delete()
        session.commit()


def _make_alert_payload():
    return {
        "service": "payment-api",
        "alert_type": "high_error_rate",
        "severity": "P3",
        "description": "Error rate elevated",
        "metric_value": 0.25,
        "threshold": 0.10,
    }


def test_resolved_incident_survives_orchestrator_recreation():
    orch1 = IncidentResponseOrchestrator()
    fake_crew = MagicMock()
    fake_crew.kickoff.return_value = '{"root_cause": "x", "confidence": 0.9}'
    with patch("src.orchestrator.create_incident_response_crew", return_value=fake_crew):
        result = orch1.process_alert(_make_alert_payload(), incident_id="persist-test-1")
    assert result["incident_id"] == "persist-test-1"

    orch2 = IncidentResponseOrchestrator()
    incident = orch2.get_incident("persist-test-1")
    assert incident["status"] != "not_found"
    assert "summary" in incident


def test_get_incident_returns_not_found_for_unknown():
    orch = IncidentResponseOrchestrator()
    assert orch.get_incident("no-such-id")["status"] == "not_found"


def test_list_resolved_incidents_returns_dict():
    orch = IncidentResponseOrchestrator()
    fake_crew = MagicMock()
    fake_crew.kickoff.return_value = '{"root_cause": "x", "confidence": 0.9}'
    with patch("src.orchestrator.create_incident_response_crew", return_value=fake_crew):
        orch.process_alert(_make_alert_payload(), incident_id="list-test-1")
    resolved = orch.list_resolved_incidents()
    assert "list-test-1" in resolved
    assert "service" in resolved["list-test-1"]


def test_count_resolved_increments():
    orch = IncidentResponseOrchestrator()
    assert orch.count_resolved() == 0
    fake_crew = MagicMock()
    fake_crew.kickoff.return_value = '{"root_cause": "x", "confidence": 0.9}'
    with patch("src.orchestrator.create_incident_response_crew", return_value=fake_crew):
        orch.process_alert(_make_alert_payload(), incident_id="count-test-1")
    assert orch.count_resolved() == 1
