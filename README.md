# Intelligent Incident Response Crew

AI-powered incident response orchestration built on **CrewAI**. An alert (from PagerDuty, Datadog, or Alertmanager) hits a FastAPI webhook, which runs a 5-agent sequential crew that triages the alert, analyzes logs, finds the root cause, retrieves a runbook, and posts a summary to Slack. The pipeline is **read-only** with respect to infrastructure — it diagnoses, it does not remediate.

## Architecture

```
Alert JSON  ──►  POST /webhook/alert          (FastAPI, returns 202)
PD Event    ──►  POST /webhook/pagerduty      (PagerDuty v3 format)
                       │
                       ▼  Redis dedup (1-hour fingerprint window)
                       │
                  BackgroundTask
                       │
                       ▼
              orchestrator.process_alert()
                       │
                       ▼
         create_incident_response_crew()
                       │
          ┌────────────┼────────────────┐
          ▼            ▼                ▼
     triage_agent  log_agent       rca_agent
                                        │
                                   runbook_agent  (vector search → keyword fallback)
                                        │
                                  notifier_agent  (Slack + Jira)
                                        │
                                        ▼
                           IncidentSummary → PostgreSQL
```

**Key properties:**
- Every integration client pings its backend on init and silently falls back to realistic mock data when unreachable — the full pipeline runs locally with no infrastructure.
- `crew.kickoff()` requires a real LLM; set `LLM_MODEL` and the matching API key or the crew returns `{"status": "error"}`.
- Incident history is persisted to PostgreSQL (SQLite in dev/test).
- Alert deduplication uses Redis with a 1-hour bucket fingerprint; falls back to an in-process dict.

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env — set LLM_MODEL and the matching API key at minimum

docker compose up -d
```

This starts: **app** (port 5000) · **postgres** with pgvector (5432) · **redis** (6379) · **elasticsearch** (9200) · **prometheus** (9090).

Send a test alert:

```bash
curl -X POST http://localhost:5000/webhook/alert \
  -H "Content-Type: application/json" \
  -d '{
    "alert_id": "a1",
    "service": "payment-api",
    "alert_type": "high_error_rate",
    "severity": "P1",
    "description": "Error rate 45%",
    "metric_value": 0.45,
    "threshold": 0.10
  }'
```

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in LLM_MODEL + API key

python main.py          # serves on http://0.0.0.0:5000
```

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/webhook/alert` | HMAC-SHA256 (optional) | Generic inbound alert |
| `POST` | `/webhook/pagerduty` | HMAC-SHA256 (optional) | PagerDuty v3 event |
| `GET` | `/incident/{id}` | Bearer token (optional) | Incident status + summary |
| `GET` | `/incidents` | Bearer token (optional) | All pending + resolved incidents |
| `GET` | `/health` | — | Liveness + counts |
| `GET` | `/metrics` | Bearer token (optional) | Prometheus metrics |
| `GET` | `/docs` | — | Swagger UI |

Authentication is **opt-in**: set `WEBHOOK_SECRET` and/or `API_TOKEN` in `.env` to enable. Leave empty for dev mode.

## LLM provider

Set `LLM_MODEL` to any [LiteLLM model string](https://docs.litellm.ai/docs/providers) and the matching key:

| Provider | LLM_MODEL example | Key var |
|----------|------------------|---------|
| OpenAI | `gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| Groq | `groq/llama3-70b-8192` | `OPENAI_API_KEY` + `OPENAI_API_BASE=https://api.groq.com/openai/v1` |

`LLM_MODEL_FAST` is used for the triage and runbook agents (cheaper/faster); defaults to `gpt-4o-mini`.

## Runbook seeding (pgvector)

After the stack is up, seed the built-in runbooks into the vector store:

```bash
python scripts/seed_runbooks.py
```

Without seeding, `search_runbooks` falls back to keyword scoring automatically.

## Running tests

```bash
DATABASE_URL=sqlite:///:memory: pytest --tb=short -q
```

All 80 tests pass with no external dependencies (ES, Redis, pgvector all mock on failure).

## Tech stack

| Layer | Technology |
|-------|-----------|
| Agent framework | CrewAI |
| LLM abstraction | LiteLLM |
| HTTP server | FastAPI + Uvicorn |
| Persistence | SQLAlchemy 2 · PostgreSQL / SQLite |
| Deduplication | Redis |
| Log search | Elasticsearch |
| Metrics | Prometheus |
| Vector search | pgvector + sentence-transformers |
| Notifications | Slack SDK · Jira |
| Data validation | Pydantic v2 |

## Security notes

- Webhook HMAC-SHA256 verification is enforced only when `WEBHOOK_SECRET` is set.
- Bearer token auth on read endpoints is enforced only when `API_TOKEN` is set.
- The agent pipeline is read-only with respect to infrastructure — no automated remediation.
- Never commit `.env` (it is gitignored). Use `.env.example` as the template.

## License

MIT
