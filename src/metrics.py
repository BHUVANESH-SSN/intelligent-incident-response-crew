"""Prometheus metrics for self-monitoring the incident response system."""

import time
import logging
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

# --- Counters ---
incidents_total = Counter(
    "incident_response_incidents_total",
    "Total incidents processed",
    ["service", "severity", "status"]
)

tool_errors_total = Counter(
    "incident_response_tool_errors_total",
    "Total errors from agent tools",
    ["tool_name"]
)

# --- Histograms ---
incident_duration_seconds = Histogram(
    "incident_response_duration_seconds",
    "Time to process an incident end-to-end",
    ["service", "severity"],
    buckets=[5, 15, 30, 60, 120, 300, 600]
)

rca_confidence = Histogram(
    "incident_response_rca_confidence",
    "Root cause analysis confidence scores",
    ["service"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# --- Gauges ---
active_incidents = Gauge(
    "incident_response_active_incidents",
    "Number of currently active incidents"
)


def get_metrics_response():
    """Generate Prometheus-compatible metrics response."""
    return generate_latest(), CONTENT_TYPE_LATEST
