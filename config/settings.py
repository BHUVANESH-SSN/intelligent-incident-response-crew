"""Configuration management."""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Base configuration."""
    
    # LLM Configuration — LiteLLM model strings (e.g. "gpt-4", "anthropic/claude-sonnet-4-6")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_API_BASE = os.getenv("OPENAI_API_BASE")
    OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4")  # kept for backward-compat
    LLM_MODEL = os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL_NAME", "gpt-4"))
    LLM_MODEL_FAST = os.getenv("LLM_MODEL_FAST", "gpt-3.5-turbo")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    
    # Elasticsearch
    ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
    ELASTICSEARCH_USERNAME = os.getenv("ELASTICSEARCH_USERNAME", "elastic")
    ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD", "changeme")
    
    # Prometheus
    PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    
    # Slack
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
    
    # Confluence
    CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
    CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL")
    CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN")
    
    # Kubernetes
    KUBECONFIG = os.getenv("KUBECONFIG", "~/.kube/config")
    
    # PagerDuty
    PAGERDUTY_API_KEY = os.getenv("PAGERDUTY_API_KEY")
    
    # Webhook Security
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # HMAC-SHA256 for webhook auth
    
    # Jira
    JIRA_URL = os.getenv("JIRA_URL")
    JIRA_USERNAME = os.getenv("JIRA_USERNAME")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
    
    # Vector DB
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX = os.getenv("PINECONE_INDEX", "incident-runbooks")
    
    # Incident Response Settings
    MIN_CONFIDENCE_FOR_AUTO_FIX = 0.7  # 70% confidence required for automated remediation
    ESCALATION_THRESHOLD = 300  # Escalate after 5 minutes if not resolved
    DEFAULT_SLACK_CHANNEL = "#incidents"
    INVESTIGATION_TIMEOUT_MINS = 15  # Give up if investigation takes too long


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    MIN_CONFIDENCE_FOR_AUTO_FIX = 0.85  # Stricter in prod
    ESCALATION_THRESHOLD = 180  # Escalate faster in prod (3 mins)


def get_config():
    """Get configuration based on environment."""
    env = os.getenv("ENVIRONMENT", "development")
    if env == "production":
        return ProductionConfig()
    else:
        return DevelopmentConfig()


# Export config instance
config = get_config()
