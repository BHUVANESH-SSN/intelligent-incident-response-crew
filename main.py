"""Main entry point for incident response system."""

import os
import sys
import logging

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from src.orchestrator import orchestrator
from examples.webhook_server import app

if __name__ == "__main__":
    print("""
    ===================================================================

            INTELLIGENT INCIDENT RESPONSE CREW

            CrewAI-powered incident diagnosis & remediation

    ===================================================================

    Starting webhook server on http://0.0.0.0:5000

    Inbound webhooks:
      POST /webhook/alert        - Generic alert (PagerDuty/OpsGenie/custom)
      POST /webhook/pagerduty    - PagerDuty v3 event notifications

    Status & metrics:
      GET  /incident/{id}        - Incident status and summary
      GET  /incidents            - List all pending + resolved incidents
      GET  /health               - Health check (counts, liveness)
      GET  /metrics              - Prometheus metrics
      GET  /docs                 - Swagger UI

    Example alert:
      curl -X POST http://localhost:5000/webhook/alert \\
        -H "Content-Type: application/json" \\
        -d '{
          "alert_id": "alert-001",
          "service": "payment-api",
          "alert_type": "high_error_rate",
          "severity": "P1",
          "description": "Error rate exceeded 10%",
          "metric_value": 0.45,
          "threshold": 0.10
        }'

    Press Ctrl+C to stop.
    """)
    
    import uvicorn
    uvicorn.run("examples.webhook_server:app", host="0.0.0.0", port=5000)
