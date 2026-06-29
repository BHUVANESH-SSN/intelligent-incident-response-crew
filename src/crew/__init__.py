"""CrewAI crew definition for incident response."""

import logging
from crewai import Agent, Task, Crew, Process
from langchain_community.chat_models import ChatLiteLLM
from config.settings import config
from src.tools import (
    fetch_logs,
    get_error_patterns,
    query_metrics,
    get_service_metrics,
    get_deployment_info,
    search_runbooks,
    post_slack_message,
    create_jira_ticket
)

logger = logging.getLogger(__name__)


def _make_llm(model: str) -> ChatLiteLLM:
    return ChatLiteLLM(model=model)


def _make_agents(llm, llm_fast):
    triage_agent = Agent(
        role="Incident Triage Specialist",
        goal="Quickly classify alert severity, extract context, and determine if this is a real incident or noise",
        backstory="""You are an expert at reading monitoring alerts and distinguishing between
    real incidents and false positives. You understand SLOs, error budgets, and can quickly
    assess if an alert warrants investigation. You have years of experience in on-call and
    can smell a real problem from a mile away.""",
        tools=[get_service_metrics, query_metrics],
        llm=llm_fast,
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
        llm=llm,
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
        llm=llm,
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
        llm=llm_fast,
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
        tools=[post_slack_message, create_jira_ticket],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3
    )

    return triage_agent, log_agent, rca_agent, runbook_agent, notifier_agent


def create_incident_tasks(alert_context: dict, agents: tuple):
    """Create tasks for incident investigation."""
    triage_agent, log_agent, rca_agent, runbook_agent, notifier_agent = agents

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
        description=f"""Create a comprehensive incident summary for Slack and emit a structured result.

1. Compose a clear, human-readable Slack summary covering:
   - Service affected: {alert_context.get('service')}
   - Root cause: (from RCA agent)
   - Confidence: (from RCA agent)
   - Remediation steps: (from Runbook agent)
   - Business impact: (from Triage agent)
   - Current status: investigating

2. Post that summary to the '{config.DEFAULT_SLACK_CHANNEL}' channel using the
   post_slack_message tool (channel='{config.DEFAULT_SLACK_CHANNEL}', message_type='summary',
   data=<the summary fields>).

3. If the confirmed severity is P1 or P2, create a Jira tracking ticket using the
   create_jira_ticket tool (service='{alert_context.get('service')}', severity=<confirmed severity>,
   summary=<one-line incident title>, description=<root cause, business impact, and remediation steps>).
   Capture the returned "ticket_url". For P3/P4 incidents, do NOT create a ticket and use null.

4. After posting, your FINAL output MUST be a single JSON object (and nothing after it)
   that the orchestrator can parse, with exactly these keys:
   - "root_cause": string (the primary root cause from the RCA agent)
   - "confidence": number between 0.0 and 1.0 (convert any 0-100 score to a 0.0-1.0 fraction)
   - "next_steps": list of strings (recommended actions / follow-ups)
   - "severity": string (the confirmed severity, e.g. "P1")
   - "remediation_steps": list of strings (from the Runbook agent)
   - "business_impact": string (from the Triage agent)
   - "jira_ticket_url": string URL of the Jira ticket created in step 3, or null if no ticket was created""",
        agent=notifier_agent,
        expected_output=f"""First, a clear human-readable Slack summary posted to '{config.DEFAULT_SLACK_CHANNEL}' with:
- Clear incident summary
- Root cause and confidence
- Recommended actions
- Link to any runbooks or escalation info
- Status indicator (investigating/resolved/escalated)

Then, as the LAST output, a single JSON object with these keys:
{{
  "root_cause": "<string>",
  "confidence": <0.0-1.0>,
  "next_steps": ["<string>", ...],
  "severity": "<string>",
  "remediation_steps": ["<string>", ...],
  "business_impact": "<string>",
  "jira_ticket_url": "<string-url-or-null>"
}}""",
    )

    return [t1, t2, t3, t4, t5]


def create_incident_response_crew(alert_context: dict) -> Crew:
    """Create and return the incident response crew with LiteLLM-backed agents."""
    llm = _make_llm(config.LLM_MODEL)
    llm_fast = _make_llm(config.LLM_MODEL_FAST)
    agents = _make_agents(llm, llm_fast)
    tasks = create_incident_tasks(alert_context, agents)

    crew = Crew(
        agents=list(agents),
        tasks=tasks,
        process=Process.sequential,
        memory=False,
        verbose=True,
    )

    return crew
