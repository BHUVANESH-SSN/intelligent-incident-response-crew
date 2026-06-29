"""Convert PagerDuty v3 webhook payloads to internal alert format."""

import uuid
from typing import Any

_URGENCY_TO_SEVERITY = {
    "high": "P1",
    "low": "P3",
}


def parse_pagerduty_alert(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse a PagerDuty v3 webhook event into our internal alert dict.

    Raises KeyError if the top-level 'event' key is missing.
    """
    event = payload["event"]
    data = event.get("data", {})

    urgency = data.get("urgency", "low")
    severity = _URGENCY_TO_SEVERITY.get(urgency, "P2")

    service_name = data.get("service", {}).get("name", "unknown")
    title = data.get("title", "PagerDuty incident")
    details = data.get("body", {}).get("details", "")
    description = f"{title}. {details}".strip(". ") if details else title

    return {
        "alert_id": data.get("id", str(uuid.uuid4())),
        "service": service_name,
        "alert_type": "pagerduty",
        "severity": severity,
        "description": description,
        "metric_value": None,
        "threshold": None,
        "source": "pagerduty",
    }
