"""Main incident response orchestrator."""

import os
import json
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

from src.models.incident import Alert, IncidentContext, IncidentSummary, IncidentStatus, SeverityLevel
from src.crew import create_incident_response_crew
from src.metrics import (
    incidents_total, incident_duration_seconds,
    rca_confidence, active_incidents
)
from config.settings import config

logger = logging.getLogger(__name__)


class IncidentResponseOrchestrator:
    """Main orchestrator for incident response workflow."""
    
    def __init__(self):
        self.pending_incidents: Dict[str, IncidentContext] = {}
        self.resolved_incidents: Dict[str, IncidentSummary] = {}
    
    def process_alert(self, alert_payload: Dict[str, Any], incident_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process an incoming alert and trigger the incident response crew.

        Args:
            alert_payload: Alert data from monitoring system
            incident_id: Optional pre-generated incident ID (defaults to new UUID if not provided)

        Returns:
            Investigation results and incident summary
        """
        if incident_id is None:
            incident_id = str(uuid.uuid4())
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
            elapsed_minutes = (time.time() - start_time) / 60.0
            summary = self._process_crew_result(
                incident_id,
                alert,
                result,
                elapsed_minutes
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
                status="escalated" if summary.escalated else "completed"
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
                "status": "escalated" if summary.escalated else "completed",
                "duration_seconds": round(duration, 1),
                "summary": summary.model_dump(),
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
        crew_result,
        duration_minutes: float = 0.0
    ) -> IncidentSummary:
        """Process crew result into incident summary."""

        # Parse the crew output (structured or unstructured). The model may wrap
        # the JSON in markdown fences or prose, so extract the last {...} block.
        result_data = self._extract_json(str(crew_result) if crew_result else "")

        # Create summary
        summary = IncidentSummary(
            incident_id=incident_id,
            service=alert.service,
            severity=alert.severity,
            status=IncidentStatus.RESOLVED,
            duration_minutes=round(duration_minutes, 2),
            root_cause=result_data.get("root_cause", str(crew_result)[:300] if crew_result else "Investigation in progress"),
            root_cause_confidence=result_data.get("confidence", 0.5),
            investigation_notes=str(crew_result)[:500] if crew_result else "",
            next_steps=result_data.get("next_steps", ["Review incident", "Monitor service metrics"]),
        )

        # Decide whether a human needs to be pulled in.
        self._evaluate_escalation(summary, duration_minutes)

        return summary

    def _evaluate_escalation(self, summary: IncidentSummary, duration_minutes: float) -> None:
        """Decide whether an incident needs human escalation and annotate the summary.

        Escalates when the crew's confidence is too low to act on, when the
        investigation ran past the configured time budget, or for the most
        severe incidents which always warrant a human on-call. Sets
        ``escalated``, ``escalation_reason`` and flips the status to ESCALATED.
        """
        reasons = []

        if summary.root_cause_confidence < config.MIN_CONFIDENCE_FOR_AUTO_FIX:
            reasons.append(
                f"root cause confidence {summary.root_cause_confidence:.0%} is below "
                f"the {config.MIN_CONFIDENCE_FOR_AUTO_FIX:.0%} action threshold"
            )

        if duration_minutes * 60 > config.ESCALATION_THRESHOLD:
            reasons.append(
                f"investigation took {duration_minutes:.1f} min, exceeding the "
                f"{config.ESCALATION_THRESHOLD / 60:.1f} min escalation threshold"
            )

        if summary.severity == SeverityLevel.P1:
            reasons.append("P1 severity requires human on-call engagement")

        if reasons:
            summary.escalated = True
            summary.escalation_reason = "; ".join(reasons)
            summary.status = IncidentStatus.ESCALATED
            logger.info(
                f"Incident {summary.incident_id} escalated: {summary.escalation_reason}"
            )

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract a JSON object from raw crew output.

        The output may be a bare JSON object, JSON wrapped in markdown code
        fences, or JSON embedded in prose. Returns the last parseable {...}
        block, falling back to an empty dict when none is found.
        """
        if not text:
            return {}

        # Fast path: the whole string is a JSON object.
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        # Scan for the last balanced {...} block and try to parse it.
        end = text.rfind("}")
        while end != -1:
            depth = 0
            start = -1
            for i in range(end, -1, -1):
                ch = text[i]
                if ch == "}":
                    depth += 1
                elif ch == "{":
                    depth -= 1
                    if depth == 0:
                        start = i
                        break
            if start != -1:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
                # Try an earlier closing brace.
                end = text.rfind("}", 0, start)
            else:
                break

        return {}
    
    def get_incident(self, incident_id: str) -> Dict[str, Any]:
        """Get incident details."""
        if incident_id in self.resolved_incidents:
            return {
                "status": "resolved",
                "summary": self.resolved_incidents[incident_id].model_dump()
            }
        elif incident_id in self.pending_incidents:
            return {
                "status": "investigating",
                "alert": self.pending_incidents[incident_id].alert.model_dump()
            }
        else:
            return {"status": "not_found"}


# Global orchestrator instance
orchestrator = IncidentResponseOrchestrator()
