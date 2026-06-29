"""Tests for IncidentResponseOrchestrator result parsing and process_alert.

Hermetic: no live LLM. `create_incident_response_crew` (imported into
src.orchestrator) is patched so crew.kickoff returns a canned string.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.models.incident import Alert, SeverityLevel, IncidentStatus
from src.orchestrator import IncidentResponseOrchestrator


@pytest.fixture
def orch():
    """A fresh orchestrator instance (avoids singleton state leakage)."""
    return IncidentResponseOrchestrator()


@pytest.fixture
def alert():
    return Alert(
        alert_id="a-1",
        service="payment-api",
        alert_type="high_error_rate",
        severity=SeverityLevel.P1,
        description="Error rate 45%",
        metric_value=0.45,
        threshold=0.10,
    )


# --- _process_crew_result parsing --------------------------------------------

def test_json_in_markdown_fences_with_prose(orch, alert):
    """JSON wrapped in markdown fences + surrounding prose populates fields."""
    crew_result = (
        "Here is my final analysis of the incident.\n\n"
        "```json\n"
        "{\n"
        '  "root_cause": "Memory leak in PaymentCache",\n'
        '  "confidence": 0.87,\n'
        '  "next_steps": ["Restart pods", "Profile heap"]\n'
        "}\n"
        "```\n\n"
        "Let me know if you need anything else."
    )
    summary = orch._process_crew_result("inc1", alert, crew_result, 3.5)

    assert summary.root_cause == "Memory leak in PaymentCache"
    assert summary.root_cause_confidence == 0.87
    assert summary.next_steps == ["Restart pods", "Profile heap"]


def test_bare_json(orch, alert):
    """A bare JSON object parses directly."""
    crew_result = json.dumps(
        {
            "root_cause": "Connection pool exhaustion",
            "confidence": 0.72,
            "next_steps": ["Increase pool size"],
        }
    )
    summary = orch._process_crew_result("inc2", alert, crew_result, 1.0)

    assert summary.root_cause == "Connection pool exhaustion"
    assert summary.root_cause_confidence == 0.72
    assert summary.next_steps == ["Increase pool size"]


def test_prose_no_json_falls_back(orch, alert):
    """Prose with no JSON falls back gracefully to defaults."""
    crew_result = "The investigation is ongoing. No structured output available."
    summary = orch._process_crew_result("inc3", alert, crew_result, 2.0)

    assert summary.root_cause_confidence == 0.5
    assert summary.next_steps == ["Review incident", "Monitor service metrics"]
    # root_cause falls back to truncated raw text
    assert "investigation" in summary.root_cause.lower()


def test_last_json_block_wins(orch, alert):
    """When multiple {...} blocks exist, the last balanced block is used."""
    crew_result = (
        'A draft thought: {"root_cause": "draft", "confidence": 0.1}\n'
        'Final answer:\n{"root_cause": "Disk full on node-3", "confidence": 0.9}'
    )
    summary = orch._process_crew_result("inc4", alert, crew_result, 0.5)
    assert summary.root_cause == "Disk full on node-3"
    assert summary.root_cause_confidence == 0.9


def test_duration_minutes_is_number(orch, alert):
    """duration_minutes is populated as a number."""
    summary = orch._process_crew_result("inc5", alert, '{"root_cause": "x"}', 4.25)
    assert isinstance(summary.duration_minutes, (int, float))
    assert summary.duration_minutes == 4.25


# --- process_alert (crew boundary patched) -----------------------------------

def _make_fake_crew(canned_output):
    crew = MagicMock()
    crew.kickoff.return_value = canned_output
    return crew


def test_process_alert_completed_and_moves_to_resolved(orch, alert):
    canned = (
        "Final report:\n```json\n"
        '{"root_cause": "OOM in payment-api", "confidence": 0.81, '
        '"next_steps": ["Restart", "Add heap dump"]}\n```'
    )
    # P3 + high confidence + fast => stays RESOLVED (no escalation).
    # Escalation triggers are covered in test_escalation.py.
    payload = {
        "alert_id": "a-1",
        "service": "payment-api",
        "alert_type": "high_error_rate",
        "severity": "P3",
        "description": "Error rate 45%",
        "metric_value": 0.45,
        "threshold": 0.10,
    }

    with patch(
        "src.orchestrator.create_incident_response_crew",
        return_value=_make_fake_crew(canned),
    ) as mk:
        result = orch.process_alert(payload)

    assert mk.called
    assert result["status"] == "completed"

    incident_id = result["incident_id"]
    summary = result["summary"]
    assert summary["root_cause"] == "OOM in payment-api"
    assert summary["root_cause_confidence"] == 0.81
    assert summary["next_steps"] == ["Restart", "Add heap dump"]
    assert summary["status"] == IncidentStatus.RESOLVED.value
    assert summary["escalated"] is False

    # Incident moved from pending to resolved
    assert incident_id not in orch.pending_incidents
    assert incident_id in orch.resolved_incidents
    assert isinstance(summary["duration_minutes"], (int, float))


def test_process_alert_does_not_call_real_llm(orch, alert):
    """kickoff is the only crew interaction and it is the mock.
    Confidence 0.5 < 0.7 threshold, so this incident escalates."""
    fake_crew = _make_fake_crew('{"root_cause": "x", "confidence": 0.5}')
    payload = {
        "service": "svc",
        "severity": "P2",
        "description": "something",
    }
    with patch(
        "src.orchestrator.create_incident_response_crew", return_value=fake_crew
    ):
        result = orch.process_alert(payload)

    fake_crew.kickoff.assert_called_once()
    assert result["status"] == "escalated"
