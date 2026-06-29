"""Webhook server for receiving alerts with async processing and authentication."""

import os
import json
import hmac
import hashlib
import logging
import uuid
import sys
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import Response, JSONResponse
import uvicorn

# Ensure src is in path if not already
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestrator import orchestrator
from src.integrations.redis_client import RedisDeduplicator
from src.dedup import compute_fingerprint
from src.parsers.pagerduty import parse_pagerduty_alert

deduplicator = RedisDeduplicator()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Incident Response Webhook Server")

# --- Authentication Middleware ---

def _verify_webhook_sig(raw_body: bytes, headers) -> None:
    """Raise HTTPException if the HMAC-SHA256 webhook signature is invalid.

    If WEBHOOK_SECRET is not set, authentication is skipped (dev mode).
    Expects header: X-Webhook-Signature: sha256=<hex-digest>
    """
    webhook_secret = os.getenv("WEBHOOK_SECRET")
    if not webhook_secret:
        return
    signature = headers.get("X-Webhook-Signature", "")
    if not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing or invalid signature header")
    expected = hmac.new(
        webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature[7:]):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")


async def _verify_api_token(request: Request) -> None:
    """Verify bearer token for protected read endpoints.

    If API_TOKEN is not set, authentication is skipped (dev mode).
    Expects header: Authorization: Bearer <token>
    """
    api_token = os.getenv("API_TOKEN")
    if not api_token:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    if not hmac.compare_digest(auth[7:], api_token):
        raise HTTPException(status_code=403, detail="Invalid API token")


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

@app.post("/webhook/alert", status_code=202)
async def receive_alert(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for receiving alerts from PagerDuty/OpsGenie.
    Processes alerts asynchronously so the webhook responds immediately.
    """
    raw_body = await request.body()
    _verify_webhook_sig(raw_body, request.headers)
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Request body must be JSON")
        
    # Validate required fields
    required_fields = ["service", "severity", "description"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")
        
    # Generate incident ID if not provided
    if "alert_id" not in data:
        data["alert_id"] = str(uuid.uuid4())

    # Deduplication — same alert in the same hour returns the existing investigation
    fingerprint = compute_fingerprint(data)
    existing_id = deduplicator.check(fingerprint)
    if existing_id:
        logger.info(f"Duplicate alert detected — returning existing incident {existing_id}")
        return JSONResponse(status_code=200, content={
            "status": "deduplicated",
            "incident_id": existing_id,
            "message": "Duplicate alert — investigation already in progress",
        })

    incident_id = str(uuid.uuid4())
    deduplicator.set(fingerprint, incident_id)
    logger.info(f"Received alert for {data.get('service')}, incident: {incident_id}")
    
    # Process asynchronously via FastAPI Background Tasks
    background_tasks.add_task(_process_alert_async, incident_id, data)
    
    return {
        "status": "received",
        "incident_id": incident_id,
        "message": "Alert processing started in background"
    }

@app.post("/webhook/pagerduty", status_code=202)
async def receive_pagerduty(request: Request, background_tasks: BackgroundTasks):
    """
    Inbound webhook for PagerDuty v3 event notifications.
    Converts the PagerDuty event format to the internal alert schema and
    feeds it through the same dedup + crew pipeline as /webhook/alert.
    """
    raw_body = await request.body()
    _verify_webhook_sig(raw_body, request.headers)
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Request body must be JSON")

    try:
        data = parse_pagerduty_alert(payload)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid PagerDuty payload: {exc}")

    fingerprint = compute_fingerprint(data)
    existing_id = deduplicator.check(fingerprint)
    if existing_id:
        logger.info(f"Duplicate PagerDuty alert — returning existing incident {existing_id}")
        return JSONResponse(status_code=200, content={
            "status": "deduplicated",
            "incident_id": existing_id,
            "message": "Duplicate alert — investigation already in progress",
        })

    incident_id = str(uuid.uuid4())
    deduplicator.set(fingerprint, incident_id)
    logger.info(f"Received PagerDuty alert for {data.get('service')}, incident: {incident_id}")

    background_tasks.add_task(_process_alert_async, incident_id, data)

    return {
        "status": "received",
        "incident_id": incident_id,
        "message": "Alert processing started in background",
    }


@app.get("/incident/{incident_id}", dependencies=[Depends(_verify_api_token)])
async def get_incident(incident_id: str):
    """Get incident status and details."""
    try:
        incident = orchestrator.get_incident(incident_id)
        return incident
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/incidents", dependencies=[Depends(_verify_api_token)])
async def list_incidents():
    """List all incidents (pending and resolved)."""
    try:
        pending = {
            k: {"status": "investigating", "service": v.alert.service, "severity": v.severity.value}
            for k, v in orchestrator.pending_incidents.items()
        }
        resolved = orchestrator.list_resolved_incidents()
        return {
            "pending": pending,
            "resolved": resolved,
            "total_pending": len(pending),
            "total_resolved": len(resolved)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/metrics", dependencies=[Depends(_verify_api_token)])
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
        "resolved_incidents": orchestrator.count_resolved()
    }

if __name__ == "__main__":
    print("Starting Incident Response Webhook Server...")
    print("Listen on http://0.0.0.0:5000")
    print()
    print("Endpoints:")
    print("  POST /webhook/alert   - Receive alerts")
    print("  GET  /incident/{id}   - Get incident status")
    print("  GET  /incidents       - List all incidents")
    print("  GET  /health          - Health check")
    print("  GET  /docs            - Swagger UI APIs")
    print()
    uvicorn.run(app, host="0.0.0.0", port=5000)
