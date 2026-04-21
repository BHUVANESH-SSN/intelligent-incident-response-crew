"""Main incident response orchestrator."""

import os
import json
import logging
import time
from typing import Dict, Any
from datetime import datetime
import uuid

from src.models.incident import Alert, IncidentContext, IncidentSummary, IncidentStatus, SeverityLevel
from src.crew import create_incident_response_crew
from src.metrics import (
    incidents_total, incident_duration_seconds,
    rca_confidence, active_incidents
)

logger = logging.getLogger(__name__)


class IncidentResponseOrchestrator:
    """Main orchestrator for incident response workflow."""
    
    def __init__(self):
        self.pending_incidents: Dict[str, IncidentContext] = {}
        self.resolved_incidents: Dict[str, IncidentSummary] = {}
    
    def process_alert(self, alert_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an incoming alert and trigger the incident response crew.
        
        Args:
            alert_payload: Alert data from monitoring system
            
        Returns:
            Investigation results and incident summary
        """
        incident_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        try:
            # Parse alert into our model
            alert = self._parse_alert(alert_payload)
            
            logger.info(f"Processing alert for {alert.service} (incident: {incident_id})")
            
            # Create incident context
            context = IncidentContext(alert=alert, severity=alert.severity)
            self.pending_incidents[incident_id] = context
            active_incidents.inc()
            
            # Create and run the crew
            crew_input = {
                "service": alert.service,
                "alert_type": alert.alert_type,
                "severity": alert.severity.value,
                "description": alert.description,
                "metric_value": alert.metric_value,
                "threshold": alert.threshold,
            }
            
            crew = create_incident_response_crew(crew_input)
            logger.info(f"Starting incident response crew for {incident_id}")
            
            # Run the crew
            result = crew.kickoff(inputs=crew_input)
            
            # Process results
            summary = self._process_crew_result(
                incident_id,
                alert,
                result
            )
            
            # Move to resolved
            del self.pending_incidents[incident_id]
            self.resolved_incidents[incident_id] = summary
            active_incidents.dec()
            
            # Record metrics
            duration = time.time() - start_time
            incidents_total.labels(
                service=alert.service,
                severity=alert.severity.value,
                status="completed"
            ).inc()
            incident_duration_seconds.labels(
                service=alert.service,
                severity=alert.severity.value
            ).observe(duration)
            rca_confidence.labels(
                service=alert.service
            ).observe(summary.root_cause_confidence)
            
            logger.info(f"Incident {incident_id} processed in {duration:.1f}s")
            
            return {
                "incident_id": incident_id,
                "status": "completed",
                "duration_seconds": round(duration, 1),
                "summary": summary.dict(),
                "raw_output": str(result)
            }
            
        except Exception as e:
            logger.exception(f"Error processing alert: {e}")
            duration = time.time() - start_time
            
            # Clean up pending
            if incident_id in self.pending_incidents:
                del self.pending_incidents[incident_id]
                active_incidents.dec()
            
            incidents_total.labels(
                service=alert_payload.get("service", "unknown"),
                severity=alert_payload.get("severity", "unknown"),
                status="error"
            ).inc()
            
            return {
                "incident_id": incident_id,
                "status": "error",
                "duration_seconds": round(duration, 1),
                "error": str(e)
            }
    
    def _parse_alert(self, alert_payload: Dict[str, Any]) -> Alert:
        """Parse alert payload into Alert model."""
        return Alert(
            alert_id=alert_payload.get("alert_id", str(uuid.uuid4())),
            service=alert_payload.get("service", "unknown"),
            alert_type=alert_payload.get("alert_type", "generic"),
            severity=SeverityLevel(alert_payload.get("severity", "P3")),
            description=alert_payload.get("description", ""),
            metric_value=alert_payload.get("metric_value"),
            threshold=alert_payload.get("threshold"),
            affected_region=alert_payload.get("region"),
        )
    
    def _process_crew_result(
        self,
        incident_id: str,
        alert: Alert,
        crew_result
    ) -> IncidentSummary:
        """Process crew result into incident summary."""
        
        # Parse the crew output (structured or unstructured)
        try:
            result_str = str(crew_result)
            result_data = json.loads(result_str) if result_str.startswith("{") else {}
        except (json.JSONDecodeError, TypeError):
            result_data = {}
        
        # Create summary
        summary = IncidentSummary(
            incident_id=incident_id,
            service=alert.service,
            severity=alert.severity,
            status=IncidentStatus.RESOLVED,
            duration_minutes=0,  # Would calculate from actual timing
            root_cause=result_data.get("root_cause", str(crew_result)[:300] if crew_result else "Investigation in progress"),
            root_cause_confidence=result_data.get("confidence", 0.5),
            investigation_notes=str(crew_result)[:500] if crew_result else "",
            next_steps=result_data.get("next_steps", ["Review incident", "Monitor service metrics"]),
        )
        
        return summary
    
    def get_incident(self, incident_id: str) -> Dict[str, Any]:
        """Get incident details."""
        if incident_id in self.resolved_incidents:
            return {
                "status": "resolved",
                "summary": self.resolved_incidents[incident_id].dict()
            }
        elif incident_id in self.pending_incidents:
            return {
                "status": "investigating",
                "alert": self.pending_incidents[incident_id].alert.dict()
            }
        else:
            return {"status": "not_found"}


# Global orchestrator instance
orchestrator = IncidentResponseOrchestrator()
