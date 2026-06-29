"""Tools for CrewAI agents."""

import os
import json
import logging
from typing import Any
from crewai_tools import tool
from src.integrations.elasticsearch_client import ElasticsearchClient
from src.integrations.prometheus_client import PrometheusClient
from src.integrations.slack_client import SlackClient
from src.integrations.jira_client import JiraClient
from src.integrations.vector_store import VectorStoreClient
from src.metrics import tool_errors_total

logger = logging.getLogger(__name__)

# Initialize clients
es_client = ElasticsearchClient()
prom_client = PrometheusClient()
slack_client = SlackClient()
jira_client = JiraClient()
vector_store_client = VectorStoreClient()

RUNBOOKS = {
    "high_memory_usage": {
        "title": "Memory Leak Investigation & Remediation",
        "keywords": ["memory", "oom", "outofmemory", "heap", "gc", "leak", "ram"],
        "severity": "P1-P2",
        "steps": [
            "1. Check current heap usage: kubectl top pods -l app=<service>",
            "2. Capture heap dump: jmap -dump:live,format=b,file=heapdump.hprof <pid>",
            "3. Look for unbounded caches or growing collections",
            "4. Verify connection pool max-size settings",
            "5. Check for unclosed resources (streams, connections)"
        ],
        "quick_fix": "Restart pods with rolling update: kubectl rollout restart deployment/<service>",
        "long_term_fix": "Profile heap usage, fix leak source, add -XX:+HeapDumpOnOutOfMemoryError"
    },
    "high_error_rate": {
        "title": "Error Rate Spike Response",
        "keywords": ["error", "5xx", "500", "exception", "failure", "rate", "spike"],
        "severity": "P1-P2",
        "steps": [
            "1. Check recent deployments: kubectl rollout history deployment/<service>",
            "2. Review application logs for new error patterns",
            "3. Check external service dependencies for failures",
            "4. Verify database connectivity and query performance",
            "5. Check for config changes in last 1 hour"
        ],
        "quick_fix": "Rollback last deployment: kubectl rollout undo deployment/<service>",
        "long_term_fix": "Add canary deployments and automated rollback on error rate threshold"
    },
    "high_latency": {
        "title": "Latency Spike Investigation",
        "keywords": ["latency", "slow", "timeout", "response", "p95", "p99", "delay", "duration"],
        "severity": "P2-P3",
        "steps": [
            "1. Check database query performance and slow query logs",
            "2. Review connection pool utilization",
            "3. Check for upstream service degradation",
            "4. Verify CPU and memory are within limits",
            "5. Check network latency between service and dependencies"
        ],
        "quick_fix": "Scale up replicas: kubectl scale deployment/<service> --replicas=<N+2>",
        "long_term_fix": "Add caching layer, optimize slow queries, implement circuit breakers"
    },
    "disk_full": {
        "title": "Disk Space Exhaustion Response",
        "keywords": ["disk", "storage", "space", "full", "inode", "volume", "pvc"],
        "severity": "P1-P2",
        "steps": [
            "1. Find largest directories: du -sh /* | sort -rh | head -20",
            "2. Check log rotation config: cat /etc/logrotate.d/<service>",
            "3. Identify old temp files: find /tmp -mtime +7 -type f",
            "4. Check for orphaned data files or snapshots",
            "5. Verify PVC auto-expansion is configured"
        ],
        "quick_fix": "Clean old logs: find /var/log -name '*.log.*' -mtime +3 -delete",
        "long_term_fix": "Implement log rotation, PVC auto-expansion, and monitoring alerts at 70%"
    },
    "high_cpu": {
        "title": "CPU Saturation Investigation",
        "keywords": ["cpu", "processor", "throttle", "utilization", "compute", "load"],
        "severity": "P2",
        "steps": [
            "1. Identify hot threads: top -H -p <pid>",
            "2. Check for infinite loops or runaway processes",
            "3. Profile with async-profiler or perf",
            "4. Review recent code changes for O(n^2) algorithms",
            "5. Verify HPA (Horizontal Pod Autoscaler) is functioning"
        ],
        "quick_fix": "Scale horizontally: kubectl scale deployment/<service> --replicas=<N+2>",
        "long_term_fix": "Profile and optimize hot paths, tune HPA thresholds"
    },
    "connection_pool_exhaustion": {
        "title": "Connection Pool Exhaustion",
        "keywords": ["connection", "pool", "exhausted", "timeout", "hikari", "database", "db", "jdbc"],
        "severity": "P1-P2",
        "steps": [
            "1. Check active connections: SELECT count(*) FROM pg_stat_activity",
            "2. Identify connection-holding queries: SELECT * FROM pg_stat_activity WHERE state != 'idle'",
            "3. Verify pool max-size vs actual connections needed",
            "4. Check for connection leak (borrow without return)",
            "5. Review transaction timeout settings"
        ],
        "quick_fix": "Restart service to reset pool: kubectl rollout restart deployment/<service>",
        "long_term_fix": "Set connection pool leak-detection-threshold, add connection timeout, fix unclosed connections"
    },
    "pod_crash_loop": {
        "title": "Pod CrashLoopBackOff Resolution",
        "keywords": ["crash", "restart", "crashloop", "backoff", "oomkilled", "pod", "container"],
        "severity": "P1",
        "steps": [
            "1. Check pod events: kubectl describe pod <pod-name>",
            "2. Check last container logs: kubectl logs <pod-name> --previous",
            "3. Verify resource limits (memory/CPU) are adequate",
            "4. Check liveness/readiness probe configuration",
            "5. Verify config maps and secrets are correctly mounted"
        ],
        "quick_fix": "If OOMKilled: increase memory limit in deployment spec",
        "long_term_fix": "Set resource requests/limits based on load testing, add startup probes for slow-starting apps"
    },
    "deployment_failure": {
        "title": "Failed Deployment Recovery",
        "keywords": ["deploy", "rollout", "release", "version", "canary", "rollback", "failed"],
        "severity": "P1-P2",
        "steps": [
            "1. Check rollout status: kubectl rollout status deployment/<service>",
            "2. View deployment events: kubectl describe deployment <service>",
            "3. Check new pod logs for startup errors",
            "4. Verify image pull is successful (imagePullBackOff?)",
            "5. Compare config/env vars between old and new version"
        ],
        "quick_fix": "Rollback: kubectl rollout undo deployment/<service>",
        "long_term_fix": "Implement progressive delivery (canary/blue-green) with automated rollback"
    },
}


@tool("fetch_logs")
def fetch_logs(service: str, window_mins: int = 30, level: str = "ERROR") -> str:
    """
    Fetch error logs from Elasticsearch for a service.
    
    Args:
        service: Service name to query
        window_mins: Time window in minutes to look back
        level: Log level (ERROR, WARN, etc.)
        
    Returns:
        JSON string of log entries
    """
    try:
        logs = es_client.fetch_logs(service, window_mins, level)
        
        # Format for readability
        formatted_logs = []
        for log in logs[:10]:  # Top 10 logs
            formatted_logs.append({
                "timestamp": str(log.get("timestamp")),
                "level": log.get("level"),
                "message": log.get("message"),
                "error_type": log.get("error", {}).get("type", "Unknown")
            })
        
        return json.dumps(formatted_logs, indent=2)
    except Exception as e:
        logger.error(f"Error in fetch_logs: {e}")
        tool_errors_total.labels(tool_name="fetch_logs").inc()
        return json.dumps({"error": str(e)})


@tool("get_error_patterns")
def get_error_patterns(service: str, window_mins: int = 30) -> str:
    """
    Get top error patterns and stack traces for a service.
    
    Args:
        service: Service name
        window_mins: Time window in minutes
        
    Returns:
        JSON string of error patterns
    """
    try:
        patterns = es_client.fetch_error_patterns(service, window_mins)
        return json.dumps(patterns, indent=2)
    except Exception as e:
        logger.error(f"Error in get_error_patterns: {e}")
        tool_errors_total.labels(tool_name="get_error_patterns").inc()
        return json.dumps({"error": str(e)})


@tool("query_metrics")
def query_metrics(query: str) -> str:
    """
    Run a PromQL query against Prometheus.
    
    Args:
        query: PromQL query string
        
    Returns:
        JSON string of query results
    """
    try:
        results = prom_client.query_metrics(query)
        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error in query_metrics: {e}")
        tool_errors_total.labels(tool_name="query_metrics").inc()
        return json.dumps({"error": str(e)})


@tool("get_service_metrics")
def get_service_metrics(service: str) -> str:
    """
    Get current metrics for a service (error rate, latency, CPU, memory).
    
    Args:
        service: Service name
        
    Returns:
        JSON string of current metrics
    """
    try:
        metrics = prom_client.get_service_metrics(service)
        return json.dumps(metrics, indent=2)
    except Exception as e:
        logger.error(f"Error in get_service_metrics: {e}")
        tool_errors_total.labels(tool_name="get_service_metrics").inc()
        return json.dumps({"error": str(e)})


@tool("get_deployment_info")
def get_deployment_info(service: str) -> str:
    """
    Get recent deployment information for a service.
    
    Args:
        service: Service name
        
    Returns:
        JSON string of deployment info
    """
    try:
        deployments = prom_client.get_deployment_info(service)
        return json.dumps(deployments, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error in get_deployment_info: {e}")
        tool_errors_total.labels(tool_name="get_deployment_info").inc()
        return json.dumps({"error": str(e)})


def _keyword_search_runbooks(symptom: str) -> str:
    """Fuzzy keyword scoring over RUNBOOKS; returns JSON string of a list of matches."""
    search_terms = symptom.lower().replace("_", " ").replace("-", " ").split()
    scored_results = []

    for key, runbook in RUNBOOKS.items():
        score = 0
        keywords = runbook["keywords"]
        if symptom.lower().replace(" ", "_") in key:
            score += 10
        for term in search_terms:
            for kw in keywords:
                if term in kw or kw in term:
                    score += 3
                elif len(term) > 3 and (term[:4] in kw or kw[:4] in term[:8]):
                    score += 1
        if score > 0:
            scored_results.append((score, key, runbook))

    scored_results.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, key, runbook in scored_results[:3]:
        output = {k: v for k, v in runbook.items() if k != "keywords"}
        output["key"] = key
        output["match_score"] = score
        results.append(output)

    if not results:
        results.append({
            "message": "No matching runbooks found for the given symptom.",
            "suggestion": "Try broader search terms like: memory, error, latency, disk, cpu, connection, crash, deploy",
        })

    return json.dumps(results, indent=2)


@tool("search_runbooks")
def search_runbooks(symptom: str) -> str:
    """
    Search runbooks for symptoms/patterns. Tries semantic vector search first,
    falls back to fuzzy keyword matching when the vector store is unavailable.

    Args:
        symptom: Symptom or error pattern to search for

    Returns:
        JSON string list of matching runbooks with remediation steps
    """
    try:
        vector_results = vector_store_client.search(symptom, top_k=3)
        if vector_results:
            return json.dumps(vector_results, indent=2)
    except Exception as e:
        logger.debug(f"Vector search unavailable, falling back to keyword: {e}")

    return _keyword_search_runbooks(symptom)


@tool("create_jira_ticket")
def create_jira_ticket(
    service: str,
    severity: str,
    summary: str,
    description: str = ""
) -> str:
    """
    Create a Jira incident ticket for tracking an incident.

    Use this for high-severity incidents (P1/P2) so the team has a tracked
    ticket. Falls back to a mock ticket if Jira is not reachable.

    Args:
        service: Affected service name
        severity: Incident severity (P1, P2, P3, P4)
        summary: Short one-line incident summary / title
        description: Fuller incident description (root cause, impact, next steps)

    Returns:
        JSON string with "ticket_key" and "ticket_url"
    """
    try:
        ticket = jira_client.create_incident_ticket(service, severity, summary, description)
        return json.dumps(ticket, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error in create_jira_ticket: {e}")
        tool_errors_total.labels(tool_name="create_jira_ticket").inc()
        return json.dumps({"error": str(e)})


@tool("post_slack_message")
def post_slack_message(channel: str, message_type: str, data: dict) -> str:
    """
    Post incident update to Slack.
    
    Args:
        channel: Slack channel
        message_type: Type of message (alert, summary)
        data: Message data
        
    Returns:
        Status message
    """
    try:
        if message_type == "alert":
            ts = slack_client.post_incident_alert(
                channel,
                data.get("service", "Unknown"),
                data.get("severity", "Unknown"),
                data.get("description", "")
            )
        elif message_type == "summary":
            ts = slack_client.post_incident_summary(channel, data)
        else:
            ts = None
        
        if ts:
            return json.dumps({"status": "success", "message_ts": ts})
        else:
            return json.dumps({"status": "error", "message": "Failed to post message"})
    except Exception as e:
        logger.error(f"Error in post_slack_message: {e}")
        tool_errors_total.labels(tool_name="post_slack_message").inc()
        return json.dumps({"status": "error", "message": str(e)})
