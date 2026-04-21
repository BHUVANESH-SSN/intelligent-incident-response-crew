# Intelligent Incident Response System

An enterprise-grade, AI-powered incident response orchestration system leveraging CrewAI to automatically diagnose monitoring alerts, analyze application logs, identify root causes, and provide structured remediation recommendations. Designed to significantly reduce Mean Time To Recovery (MTTR) and improve on-call efficiency.

## Overview

Traditional incident response relies on on-call engineers manually correlating alerts, logs, and metrics during high-pressure situations. This system automates the diagnostic pipeline by deploying a specialized multi-agent crew:

1. **Incident Triage Specialist**: Classifies severity and validates alert legitimacy via metrics.
2. **Log Analyzer**: Extracts error patterns, stack traces, and anomalies from centralized logging.
3. **Root Cause Analyst**: Correlates events across systems to determine the true root cause with a confidence threshold.
4. **Runbook Retriever**: Searches historical runbooks and playbooks for safe remediation steps.
5. **Incident Notifier**: Synthesizes the investigation into a structured summary for team communication (e.g., Slack).

Currently configured for the "Basic On-Call Replacement" pattern: an alert triggers a read-only diagnostic process which posts a comprehensive summary to the engineering team.

## Architecture

```text
Alert Payload -> Webhook Receiver (FastAPI) -> Orchestrator -> CrewAI Pipeline
                                                                    |-> Triage Agent
                                                                    |-> Log Agent
                                                                    |-> RCA Agent
                                                                    |-> Runbook Agent
                                                                    |-> Notifier Agent
                                                                            |
                                                                     Incident Summary (Slack)
```

## Technology Stack

* **Framework:** CrewAI, LangChain
* **LLM Engine:** Groq / OpenAI-compatible models
* **API Server:** FastAPI, Uvicorn
* **Monitoring Integrations:** Prometheus, Elasticsearch
* **Notification:** Slack SDK
* **Data Validation:** Pydantic

## Quick Start

### 1. Environment Configuration

Copy the environment template and configure your required credentials:

```bash
cp .env.example .env
```

Ensure the following critical variables are set in `.env`:
* `OPENAI_API_BASE` (e.g., `https://api.groq.com/openai/v1`)
* `OPENAI_API_KEY` (Your Groq/OpenAI key)
* `SLACK_BOT_TOKEN` (Bot OAuth Token for your workspace)

### 2. Dependency Installation

A Python 3.10+ environment is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Running the Service

The project uses FastAPI and Uvicorn for production-ready async webhooks. You can start the service manually:

```bash
uvicorn examples.webhook_server:app --host 0.0.0.0 --port 5000 --workers 4
```

Alternatively, configure the provided `incident-webhook.service` to run it as a continuous background daemon.

## Usage

When the server is running, configure your alerting platforms (Datadog, PagerDuty, PromQL Alertmanager) to POST a JSON payload to the webhook endpoint.

**Webhook Endpoint:** `http://<your-server-ip>:5000/webhook/alert`

**Example Payload:**
```json
{
  "alert_id": "alert-001",
  "service": "payment-api",
  "alert_type": "high_error_rate",
  "severity": "P1",
  "description": "Error rate exceeded 10%",
  "metric_value": 0.45,
  "threshold": 0.10
}
```

## Security and Production Guidelines

* **Stateless Diagnostics:** The current Multi-Agent pipeline operates in read-only mode regarding infrastructure, guaranteeing zero destructive side-effects during analysis.
* **Authentication:** Ensure you export a secure string as `WEBHOOK_SECRET` in your `.env` file to strictly mandate HMAC-SHA256 signature verification on incoming alerts.
* **Model Selection:** The implementation is highly sensitive to model capabilities. For complex stack-trace analysis, large-context models (`llama3-70b-8192` or `gpt-4`) are highly recommended over smaller counterparts.

## License

MIT License
