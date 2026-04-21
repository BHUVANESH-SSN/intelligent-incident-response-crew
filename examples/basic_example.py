"""Example usage of the incident response crew."""

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from src.orchestrator import orchestrator
from src.models.incident import SeverityLevel


def example_alert_1():
    """Example P1 alert - high error rate."""
    return {
        "alert_id": "alert-001",
        "service": "payment-api",
        "alert_type": "high_error_rate",
        "severity": "P1",
        "description": "Error rate on payment-api exceeded 10% (currently at 45%)",
        "metric_value": 0.45,
        "threshold": 0.10,
        "region": "us-east-1",
    }


def example_alert_2():
    """Example P2 alert - high memory usage."""
    return {
        "alert_id": "alert-002",
        "service": "cache-worker",
        "alert_type": "high_memory_usage",
        "severity": "P2",
        "description": "Memory usage on cache-worker is at 92% of allocated heap",
        "metric_value": 0.92,
        "threshold": 0.80,
        "region": "us-west-2",
    }


def example_alert_3():
    """Example P3 alert - latency spike."""
    return {
        "alert_id": "alert-003",
        "service": "user-service",
        "alert_type": "high_latency",
        "severity": "P3",
        "description": "P95 latency on user-service increased to 2.5s",
        "metric_value": 2.5,
        "threshold": 1.0,
        "region": "eu-west-1",
    }


def run_example():
    """Run incident response crew with example alert."""
    
    print("=" * 80)
    print("INTELLIGENT INCIDENT RESPONSE CREW - EXAMPLE RUN")
    print("=" * 80)
    print()
    
    # Get alert
    alert = example_alert_1()
    
    print(f"Incoming Alert:")
    print(f"  Service: {alert['service']}")
    print(f"  Severity: {alert['severity']}")
    print(f"  Type: {alert['alert_type']}")
    print(f"  Description: {alert['description']}")
    print()
    
    print("Starting incident response crew...")
    print("-" * 80)
    print()
    
    # Process alert
    result = orchestrator.process_alert(alert)
    
    print()
    print("-" * 80)
    print("Incident Response Complete")
    print()
    print(f"Incident ID: {result.get('incident_id')}")
    print(f"Status: {result.get('status')}")
    
    if result.get('status') == 'completed':
        summary = result.get('summary', {})
        print(f"\nIncident Summary:")
        print(f"  Root Cause: {summary.get('root_cause')}")
        print(f"  Confidence: {summary.get('root_cause_confidence'):.0%}")
        print(f"  Service: {summary.get('service')}")
        print(f"  Severity: {summary.get('severity')}")
    
    print()
    print("Raw crew output:")
    print("-" * 80)
    print(result.get('raw_output', 'No output'))
    
    return result


if __name__ == "__main__":
    result = run_example()
    print()
    print("=" * 80)
    print("Full result:")
    print(json.dumps(result, indent=2, default=str))
