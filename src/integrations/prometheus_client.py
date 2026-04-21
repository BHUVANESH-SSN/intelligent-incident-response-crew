"""Prometheus integration for querying metrics."""

import os
from typing import Dict, Any, List
from datetime import datetime, timedelta
import requests
import logging

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Client for querying metrics from Prometheus.
    
    Attempts real Prometheus HTTP API calls first, falls back to
    mock data if Prometheus is unavailable.
    """
    
    def __init__(self):
        self.base_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
        self.connected = False
        try:
            resp = requests.get(f"{self.base_url}/-/healthy", timeout=3)
            if resp.status_code == 200:
                self.connected = True
                logger.info(f"Connected to Prometheus at {self.base_url}")
            else:
                logger.warning(f"Prometheus at {self.base_url} returned {resp.status_code}, using mock data")
        except Exception as e:
            logger.warning(f"Prometheus connection failed ({e}), using mock data")
    
    def query_metrics(self, query: str, minutes: int = 30) -> Dict[str, Any]:
        """Run a PromQL query against Prometheus."""
        if self.connected:
            try:
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(minutes=minutes)
                
                resp = requests.get(
                    f"{self.base_url}/api/v1/query_range",
                    params={
                        "query": query,
                        "start": start_time.timestamp(),
                        "end": end_time.timestamp(),
                        "step": "60s"
                    },
                    timeout=10
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        result = data.get("data", {})
                        logger.info(f"Prometheus query successful: {query[:60]}...")
                        return result
                
                logger.warning(f"Prometheus query returned status {resp.status_code}, using mock")
            except Exception as e:
                logger.warning(f"Prometheus query failed ({e}), falling back to mock data")
        
        return self._mock_query_metrics(query)
    
    def get_service_metrics(
        self,
        service: str,
        metrics: List[str] = None
    ) -> Dict[str, Any]:
        """Get current metrics for a service."""
        if self.connected:
            try:
                queries = {
                    "error_rate": f'rate(http_requests_total{{service="{service}",status=~"5.."}}[5m]) / rate(http_requests_total{{service="{service}"}}[5m])',
                    "request_latency_p95": f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{service="{service}"}}[5m]))',
                    "cpu_usage": f'rate(container_cpu_usage_seconds_total{{container="{service}"}}[5m])',
                    "memory_usage": f'container_memory_usage_bytes{{container="{service}"}} / container_spec_memory_limit_bytes{{container="{service}"}}'
                }
                
                result = {}
                for metric_name, promql in queries.items():
                    try:
                        resp = requests.get(
                            f"{self.base_url}/api/v1/query",
                            params={"query": promql},
                            timeout=5
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            values = data.get("data", {}).get("result", [])
                            if values:
                                result[metric_name] = float(values[0].get("value", [0, 0])[1])
                            else:
                                result[metric_name] = None
                        else:
                            result[metric_name] = None
                    except Exception:
                        result[metric_name] = None
                
                # If we got any real data, return it
                if any(v is not None for v in result.values()):
                    # Fill in None values with 0
                    for k in result:
                        if result[k] is None:
                            result[k] = 0.0
                    logger.info(f"Fetched real Prometheus metrics for {service}")
                    return result
                
                logger.info(f"No Prometheus metrics found for {service}, using mock data")
            except Exception as e:
                logger.warning(f"Prometheus service metrics failed ({e}), using mock data")
        
        return self._mock_service_metrics(service)
    
    def get_deployment_info(self, service: str) -> Dict[str, Any]:
        """Get recent deployment information for a service."""
        if self.connected:
            try:
                query = f'kube_deployment_status_observed_generation{{deployment="{service}"}}'
                resp = requests.get(
                    f"{self.base_url}/api/v1/query",
                    params={"query": query},
                    timeout=5
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("data", {}).get("result", [])
                    if results:
                        logger.info(f"Fetched real deployment info for {service}")
                        return {
                            "generation": results[0].get("value", [0, 0])[1],
                            "timestamp": datetime.utcnow().isoformat()
                        }
            except Exception as e:
                logger.warning(f"Prometheus deployment query failed ({e}), using mock data")
        
        return self._mock_deployment_info(service)
    
    # --- Mock Data Fallbacks ---
    
    def _mock_query_metrics(self, query: str) -> Dict[str, Any]:
        """Return realistic mock metric results."""
        logger.info(f"[MOCK] Generating mock Prometheus response for: {query[:60]}...")
        
        now = datetime.utcnow()
        ts = int(now.timestamp())
        
        if "error_rate" in query or "error" in query:
            return {
                "resultType": "matrix",
                "result": [
                    {"metric": {"service": "payment-api"}, "values": [
                        [ts - 600, "0.12"], [ts - 300, "0.28"], [ts, "0.45"]
                    ]}
                ]
            }
        elif "memory" in query:
            return {
                "resultType": "matrix",
                "result": [
                    {"metric": {"service": "payment-api"}, "values": [
                        [ts - 600, "0.82"], [ts - 300, "0.91"], [ts, "0.98"]
                    ]}
                ]
            }
        elif "cpu" in query:
            return {
                "resultType": "matrix",
                "result": [
                    {"metric": {"service": "payment-api"}, "values": [
                        [ts - 600, "0.65"], [ts - 300, "0.78"], [ts, "0.92"]
                    ]}
                ]
            }
        elif "latency" in query or "duration" in query:
            return {
                "resultType": "matrix",
                "result": [
                    {"metric": {"service": "payment-api"}, "values": [
                        [ts - 600, "0.35"], [ts - 300, "0.72"], [ts, "1.20"]
                    ]}
                ]
            }
        
        return {"resultType": "matrix", "result": []}
    
    def _mock_service_metrics(self, service: str) -> Dict[str, Any]:
        """Return realistic mock service metrics."""
        logger.info(f"[MOCK] Generating mock service metrics for {service}")
        return {
            "error_rate": 0.45,
            "request_latency_p95": 1.2,
            "cpu_usage": 0.92,
            "memory_usage": 0.98
        }
    
    def _mock_deployment_info(self, service: str) -> Dict[str, Any]:
        """Return realistic mock deployment info."""
        logger.info(f"[MOCK] Generating mock deployment info for {service}")
        now = datetime.utcnow()
        return {
            "v1.4.2": (now - timedelta(minutes=45)).isoformat(),
            "v1.4.1": (now - timedelta(days=2)).isoformat(),
            "v1.4.0": (now - timedelta(days=7)).isoformat()
        }
