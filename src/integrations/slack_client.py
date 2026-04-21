"""Slack integration for posting incident updates."""

import os
import logging
from typing import Optional, Dict, Any
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackClient:
    """Client for posting incident updates to Slack."""
    
    def __init__(self):
        self.client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    
    def post_incident_alert(
        self,
        channel: str,
        service: str,
        severity: str,
        description: str
    ) -> Optional[str]:
        """
        Post incident alert to Slack channel.
        
        Args:
            channel: Slack channel name or ID
            service: Service name
            severity: Severity level (P1, P2, etc.)
            description: Alert description
            
        Returns:
            Message timestamp on success
        """
        try:
            color_map = {
                "P1": "#ff0000",  # Red
                "P2": "#ff6600",  # Orange
                "P3": "#ffcc00",  # Yellow
                "P4": "#0099cc"   # Blue
            }
            
            message = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Incident Alert: {service}",
                            "emoji": False
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Severity:*\n{severity}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Service:*\n{service}"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Description:*\n{description}"
                        }
                    },
                    {
                        "type": "divider"
                    }
                ]
            }
            
            response = self.client.chat_postMessage(
                channel=channel,
                **message
            )
            
            logger.info(f"Posted incident alert to {channel}")
            return response.get("ts")
            
        except SlackApiError as e:
            logger.error(f"Error posting to Slack: {e.response['error']}")
            return None
    
    def post_incident_summary(
        self,
        channel: str,
        summary: Dict[str, Any]
    ) -> Optional[str]:
        """
        Post detailed incident summary to Slack.
        
        Args:
            channel: Slack channel name or ID
            summary: Incident summary dictionary
            
        Returns:
            Message timestamp on success
        """
        try:
            message = {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Incident Summary: {summary.get('service', 'Unknown')}",
                            "emoji": False
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Root Cause:*\n{summary.get('root_cause', 'Unknown')}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Confidence:*\n{summary.get('root_cause_confidence', 0):.0%}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Duration:*\n{summary.get('duration_minutes', 0):.1f} min"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Status:*\n{summary.get('status', 'Unknown')}"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Investigation Notes:*\n{summary.get('investigation_notes', 'None')}"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Next Steps:*\n" + "\n".join([f"• {step}" for step in summary.get('next_steps', [])])
                        }
                    }
                ]
            }
            
            if summary.get('jira_ticket_url'):
                message["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"<{summary['jira_ticket_url']}|View in Jira>"
                    }
                })
            
            response = self.client.chat_postMessage(
                channel=channel,
                **message
            )
            
            logger.info(f"Posted incident summary to {channel}")
            return response.get("ts")
            
        except SlackApiError as e:
            logger.error(f"Error posting summary to Slack: {e.response['error']}")
            return None
    
    def get_incident_channel(self, service: str) -> str:
        """
        Get or create incident channel for a service.
        
        Args:
            service: Service name
            
        Returns:
            Channel name
        """
        channel_name = f"incident-{service.lower().replace('_', '-')}"
        return channel_name
