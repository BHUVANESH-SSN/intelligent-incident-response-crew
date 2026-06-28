"""Webhook server for receiving alerts with async processing and authentication."""

import os
import json
import hmac
import hashlib
import logging
import uuid
import sys
from fastapi import FastAPI, Request, HTTPException, Depends, BackgroundTasks
from fastapi.responses import Response
import uvicorn

# Ensure src is in path if not already
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestrator import orchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Incident Response Webhook Server")

# --- Authentication Middleware ---

async def verify_webhook(request: Request):
    """Verify webhook signature using HMAC-SHA256.
    
    If WEBHOOK_SECRET is not set, authentication is skipped (dev mode).
    Expects header: X-Webhook-Signature: sha256=<hex-digest>
    """
    webhook_secret = os.getenv("WEBHOOK_SECRET")
    
    # Skip auth in dev mode (no secret configured)
    if not webhook_secret:
        return True
        
    signature = request.headers.get("X-Webhook-Signature", "")
    if not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing or invalid signature header")
        
    body = await request.body()
    expected_sig = hmac.new(
        webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()
    
    provided_sig = signature[7:]  # Strip "sha256=" prefix
    
    if not hmac.compare_digest(expected_sig, provided_sig):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    
    return True


# --- Background Processing ---

def _process_alert_async(incident_id: str, data: dict):
    """Process alert in background thread."""
    try:
        logger.info(f"[{incident_id}] Starting async alert processing")
        result = orchestrator.process_alert(data, incident_id=incident_id)
        logger.info(f"[{incident_id}] Alert processing complete: {result.get('status')}")
    except Exception as e:
        logger.exception(f"[{incident_id}] Error in async alert processing: {e}")


# --- Routes ---

@app.post("/webhook/alert", status_code=202, dependencies=[Depends(verify_webhook)])
async def receive_alert(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for receiving alerts from PagerDuty/OpsGenie.
    Processes alerts asynchronously so the webhook responds immediately.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be JSON")
        
    # Validate required fields
    required_fields = ["service", "severity", "description"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")
        
    # Generate incident ID if not provided
    if "alert_id" not in data:
        data["alert_id"] = str(uuid.uuid4())

    incident_id = str(uuid.uuid4())
    logger.info(f"Received alert for {data.get('service')}, incident: {incident_id}")
    
    # Process asynchronously via FastAPI Background Tasks
    background_tasks.add_task(_process_alert_async, incident_id, data)
    
    return {
        "status": "received",
        "incident_id": incident_id,
        "message": "Alert processing started in background"
    }

@app.get("/incident/{incident_id}")
async def get_incident(incident_id: str):
    """Get incident status and details."""
    try:
        incident = orchestrator.get_incident(incident_id)
        return incident
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/incidents")
async def list_incidents():
    """List all incidents (pending and resolved)."""
    try:
        pending = {
            k: {"status": "investigating", "service": v.alert.service, "severity": v.severity.value}
            for k, v in orchestrator.pending_incidents.items()
        }
        resolved = {
            k: {"status": "resolved", "service": v.service, "severity": v.severity.value}
            for k, v in orchestrator.resolved_incidents.items()
        }
        return {
            "pending": pending,
            "resolved": resolved,
            "total_pending": len(pending),
            "total_resolved": len(resolved)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint for self-monitoring."""
    try:
        from src.metrics import get_metrics_response
        body, content_type = get_metrics_response()
        return Response(content=body, media_type=content_type)
    except ImportError:
        logger.warning("src.metrics not available")
        return Response(content="", media_type="text/plain")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "pending_incidents": len(orchestrator.pending_incidents),
        "resolved_incidents": len(orchestrator.resolved_incidents)
    }

if __name__ == "__main__":
    print("Starting Incident Response Webhook Server...")
    print("Listen on http://localhost:5000")
    print()
    print("Endpoints:")
    print("  POST /webhook/alert   - Receive alerts")
    print("  GET  /incident/{id}   - Get incident status")
    print("  GET  /incidents       - List all incidents")
    print("  GET  /health          - Health check")
    print("  GET  /docs            - Swagger UI APIs")
    print()
    uvicorn.run("webhook_server:app", host="0.0.0.0", port=5000, reload=True)
