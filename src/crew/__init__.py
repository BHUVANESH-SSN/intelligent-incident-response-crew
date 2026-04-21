"""CrewAI crew definition for incident response."""

import logging
from crewai import Agent, Task, Crew, Process
from src.tools import (
    fetch_logs,
    get_error_patterns,
    query_metrics,
    get_service_metrics,
    get_deployment_info,
    search_runbooks,
    post_slack_message
)

logger = logging.getLogger(__name__)


# --- Agents ---

triage_agent = Agent(
    role="Incident Triage Specialist",
    goal="Quickly classify alert severity, extract context, and determine if this is a real incident or noise",
    backstory="""You are an expert at reading monitoring alerts and distinguishing between 
    real incidents and false positives. You understand SLOs, error budgets, and can quickly 
    assess if an alert warrants investigation. You have years of experience in on-call and 
    can smell a real problem from a mile away.""",
    tools=[get_service_metrics, query_metrics],
    verbose=True,
    allow_delegation=False,
    max_iter=3
)

log_agent = Agent(
    role="Log Analyzer",
    goal="Find error patterns, anomalies, and root signals in application logs",
    backstory="""You are a senior SRE who can read stack traces in their sleep. You know 
    every common error pattern, can spot NullPointerExceptions, OutOfMemory errors, and 
    connection timeouts instantly. You extract the signal from the noise and provide 
    clear timeline of what went wrong.""",
    tools=[fetch_logs, get_error_patterns],
    verbose=True,
    allow_delegation=False,
    max_iter=3
)

rca_agent = Agent(
    role="Root Cause Analyst",
    goal="Correlate logs, metrics, and deployment info to identify the true root cause with high confidence",
    backstory="""You are an experienced incident investigator with years of dealing with 
    complex distributed systems. You excel at correlating events across multiple systems, 
    logs and metrics to find the true root cause. You provide confidence scores and clear 
    evidence for your findings. You think like a detective.""",
    tools=[fetch_logs, query_metrics, get_service_metrics, get_deployment_info],
    verbose=True,
    allow_delegation=False,
    max_iter=3
)

runbook_agent = Agent(
    role="Runbook Retriever",
    goal="Find the best remediation steps and procedures for the identified root cause",
    backstory="""You have memorized every runbook and postmortem the team ever wrote. 
    You know exactly which playbook to pull for each problem. When an engineer says 
    'disk is full' or 'memory leak', you instantly provide the exact steps to fix it.""",
    tools=[search_runbooks],
    verbose=True,
    allow_delegation=False,
    max_iter=3
)

notifier_agent = Agent(
    role="Incident Notifier",
    goal="Communicate incident diagnosis and findings clearly to the team via Slack",
    backstory="""You are a clear communicator who keeps stakeholders informed and calm 
    during incidents. You provide concise summaries with all the important details. 
    You know how to escalate when needed and when to wait for the Fix Executor.""",
    tools=[post_slack_message],
    verbose=True,
    allow_delegation=False,
    max_iter=3
)


# --- Tasks ---

def create_incident_tasks(alert_context: dict):
    """Create tasks for incident investigation."""
    
    t1 = Task(
        description=f"""Analyze this alert and classify it:
Alert Details:
- Service: {alert_context.get('service', 'unknown')}
- Type: {alert_context.get('alert_type', 'unknown')}
- Severity: {alert_context.get('severity', 'P3')}
- Description: {alert_context.get('description', 'no description')}
- Metric Value: {alert_context.get('metric_value', 'unknown')}
- Threshold: {alert_context.get('threshold', 'unknown')}

Assess: Is this a real incident or false positive? How severe really is it? What's the business impact?""",
        agent=triage_agent,
        expected_output="""Clear classification with:
- Confirmed severity (P1/P2/P3/P4)
- Is it a real incident? (yes/no)
- Business impact assessment
- Initial hypothesis about root cause
- Recommended next steps""",
    )
    
    t2 = Task(
        description=f"""Fetch and analyze logs for service '{alert_context.get('service')}' 
        in the last 30 minutes. Look for:
1. Error patterns and frequency
2. Stack traces or error messages
3. Correlation with the alert time
4. Any cascading failures

Provide a clear error timeline.""",
        agent=log_agent,
        expected_output="""Detailed log analysis including:
- Timeline of errors (when did they start)
- Top error types and their frequency
- Most recent stack traces
- User-facing vs internal errors
- Any warning signs before the error spike""",
    )
    
    t3 = Task(
        description=f"""Using the log analysis and alert data, identify the root cause:
1. Correlate logs with metrics (CPU, memory, latency)
2. Check recent deployments for {alert_context.get('service')}
3. Look for external service failures
4. Consider database/infrastructure issues

Provide your root cause hypothesis with a confidence score (0-100%).""",
        agent=rca_agent,
        expected_output="""Root cause analysis with:
- Primary root cause (specific, actionable)
- Confidence score (0-100)
- Supporting evidence (logs, metrics, deploys)
- Secondary factors that contributed
- Timeline of events that led to the incident""",
    )
    
    t4 = Task(
        description="""Based on the root cause identified, find the best remediation steps:
1. Search for matching runbooks
2. Identify quick fixes vs long-term solutions
3. Assess risk of each remediation step

Provide clear, numbered remediation steps safe for immediate action.""",
        agent=runbook_agent,
        expected_output="""Remediation playbook including:
- Top 3 recommended remediation steps
- Risk level for each (low/medium/high)
- Expected outcome if remedy is successful
- Estimated time to resolve
- Escalation path if remediation fails""",
    )
    
    t5 = Task(
        description=f"""Create a comprehensive incident summary for Slack:
- Service affected: {alert_context.get('service')}
- Root cause: (from RCA agent)
- Confidence: (from RCA agent)
- Remediation steps: (from Runbook agent)
- Business impact: (from Triage agent)
- Current status: investigating

Post to #incidents channel with clear formatting.""",
        agent=notifier_agent,
        expected_output="""Slack message posted with:
- Clear incident summary
- Root cause and confidence
- Recommended actions
- Link to any runbooks or escalation info
- Status indicator (investigating/resolved/escalated)""",
    )
    
    return [t1, t2, t3, t4, t5]


def create_incident_response_crew(alert_context: dict) -> Crew:
    """Create and return the incident response crew."""
    
    tasks = create_incident_tasks(alert_context)
    
    crew = Crew(
        agents=[triage_agent, log_agent, rca_agent, runbook_agent, notifier_agent],
        tasks=tasks,
        process=Process.sequential,
        memory=False,
        verbose=True,
    )
    
    return crew
