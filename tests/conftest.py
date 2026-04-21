"""Tests and fixtures."""

import pytest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models.incident import Alert, SeverityLevel, IncidentContext


@pytest.fixture
def sample_alert():
    """Fixture: Sample alert."""
    return Alert(
        alert_id="test-alert-001",
        service="test-service",
        alert_type="high_error_rate",
        severity=SeverityLevel.P1,
        description="Test alert for high error rate",
        metric_value=0.45,
        threshold=0.10
    )


@pytest.fixture
def incident_context(sample_alert):
    """Fixture: Incident context."""
    return IncidentContext(alert=sample_alert)


class TestIncidentModels:
    """Test incident models."""
    
    def test_alert_creation(self, sample_alert):
        """Test alert creation."""
        assert sample_alert.service == "test-service"
        assert sample_alert.severity == SeverityLevel.P1
        assert sample_alert.metric_value == 0.45
    
    def test_incident_context_creation(self, incident_context):
        """Test incident context creation."""
        assert incident_context.alert.service == "test-service"
        assert incident_context.status.value == "investigating"
