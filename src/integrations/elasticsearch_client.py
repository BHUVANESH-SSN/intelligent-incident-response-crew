"""Elasticsearch integration for fetching logs."""

import os
from typing import List, Dict, Any
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch
import logging

logger = logging.getLogger(__name__)


class ElasticsearchClient:
    """Client for querying logs from Elasticsearch.
    
    Attempts real ES queries first, falls back to mock data
    if Elasticsearch is unavailable.
    """
    
    def __init__(self):
        self.host = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
        self.connected = False
        try:
            self.es = Elasticsearch(
                [self.host],
                basic_auth=(
                    os.getenv("ELASTICSEARCH_USERNAME", "elastic"),
                    os.getenv("ELASTICSEARCH_PASSWORD", "changeme")
                ),
                verify_certs=False,
                request_timeout=5
            )
            if self.es.ping():
                self.connected = True
                logger.info(f"Connected to Elasticsearch at {self.host}")
            else:
                logger.warning(f"Elasticsearch at {self.host} not reachable, using mock data")
        except Exception as e:
            logger.warning(f"Elasticsearch connection failed ({e}), using mock data")
            self.es = None
    
    def fetch_logs(
        self, 
        service: str, 
        window_mins: int = 30,
        level: str = "ERROR",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Fetch error logs from Elasticsearch for a service."""
        if self.connected and self.es:
            try:
                now = datetime.utcnow()
                start_time = now - timedelta(minutes=window_mins)
                
                query = {
                    "size": limit,
                    "sort": [{"@timestamp": {"order": "desc"}}],
                    "query": {
                        "bool": {
                            "must": [
                                {"match": {"service": service}},
                                {"match": {"level": level}}
                            ],
                            "filter": [
                                {"range": {"@timestamp": {
                                    "gte": start_time.isoformat(),
                                    "lte": now.isoformat()
                                }}}
                            ]
                        }
                    }
                }
                
                # Try common index patterns
                for index_pattern in [f"logs-{service}-*", "logs-*", "filebeat-*"]:
                    try:
                        result = self.es.search(index=index_pattern, body=query)
                        hits = result.get("hits", {}).get("hits", [])
                        if hits:
                            logs = []
                            for hit in hits:
                                src = hit.get("_source", {})
                                logs.append({
                                    "timestamp": src.get("@timestamp", src.get("timestamp")),
                                    "service": src.get("service", service),
                                    "level": src.get("level", level),
                                    "message": src.get("message", ""),
                                    "stack_trace": src.get("stack_trace", src.get("error", {}).get("stack_trace")),
                                    "error": src.get("error", {})
                                })
                            logger.info(f"Fetched {len(logs)} real logs from ES for {service}")
                            return logs
                    except Exception:
                        continue
                
                logger.info(f"No logs found in ES for {service}, returning mock data")
            except Exception as e:
                logger.warning(f"ES query failed ({e}), falling back to mock data")
        
        return self._mock_logs(service, level, window_mins)
    
    def fetch_error_patterns(
        self,
        service: str,
        window_mins: int = 30
    ) -> Dict[str, int]:
        """Get top error patterns/stack traces for a service."""
        if self.connected and self.es:
            try:
                now = datetime.utcnow()
                start_time = now - timedelta(minutes=window_mins)
                
                query = {
                    "size": 0,
                    "query": {
                        "bool": {
                            "must": [
                                {"match": {"service": service}},
                                {"match": {"level": "ERROR"}}
                            ],
                            "filter": [
                                {"range": {"@timestamp": {
                                    "gte": start_time.isoformat(),
                                    "lte": now.isoformat()
                                }}}
                            ]
                        }
                    },
                    "aggs": {
                        "error_types": {
                            "terms": {
                                "field": "error.type.keyword",
                                "size": 20
                            }
                        }
                    }
                }
                
                for index_pattern in [f"logs-{service}-*", "logs-*", "filebeat-*"]:
                    try:
                        result = self.es.search(index=index_pattern, body=query)
                        buckets = result.get("aggregations", {}).get("error_types", {}).get("buckets", [])
                        if buckets:
                            patterns = {b["key"]: b["doc_count"] for b in buckets}
                            logger.info(f"Fetched {len(patterns)} real error patterns from ES for {service}")
                            return patterns
                    except Exception:
                        continue
                
                logger.info(f"No error patterns in ES for {service}, returning mock data")
            except Exception as e:
                logger.warning(f"ES aggregation failed ({e}), falling back to mock data")
        
        return self._mock_error_patterns()
    
    # --- Mock Data Fallbacks ---
    
    def _mock_logs(self, service: str, level: str, window_mins: int) -> List[Dict[str, Any]]:
        """Return realistic mock log entries for demo/dev mode."""
        logger.info(f"[MOCK] Generating mock {level} logs for {service}")
        if level != "ERROR":
            return []
        
        now = datetime.utcnow()
        return [
            {
                "timestamp": (now - timedelta(minutes=1)).isoformat(),
                "service": service,
                "level": "ERROR",
                "message": "java.lang.OutOfMemoryError: Java heap space",
                "stack_trace": "at com.payment.api.processor.PaymentProcessor.process(PaymentProcessor.java:42)\n"
                               "at com.payment.api.controller.PaymentController.handlePayment(PaymentController.java:78)\n"
                               "at org.springframework.web.servlet.FrameworkServlet.service(FrameworkServlet.java:897)",
                "error": {"type": "OutOfMemoryError"}
            },
            {
                "timestamp": (now - timedelta(minutes=3)).isoformat(),
                "service": service,
                "level": "ERROR",
                "message": "java.lang.OutOfMemoryError: GC overhead limit exceeded",
                "stack_trace": "at com.payment.api.cache.PaymentCache.put(PaymentCache.java:156)\n"
                               "at com.payment.api.processor.PaymentProcessor.cacheResult(PaymentProcessor.java:95)",
                "error": {"type": "OutOfMemoryError"}
            },
            {
                "timestamp": (now - timedelta(minutes=5)).isoformat(),
                "service": service,
                "level": "ERROR",
                "message": "org.apache.http.conn.ConnectionPoolTimeoutException: Timeout waiting for connection from pool",
                "stack_trace": "at org.apache.http.impl.conn.PoolingHttpClientConnectionManager.leaseConnection(PoolingHttpClientConnectionManager.java:306)",
                "error": {"type": "ConnectionPoolTimeoutException"}
            },
            {
                "timestamp": (now - timedelta(minutes=8)).isoformat(),
                "service": service,
                "level": "ERROR",
                "message": "com.zaxxer.hikari.pool.HikariPool$PoolInitializationException: Failed to initialize pool",
                "stack_trace": "at com.zaxxer.hikari.pool.HikariPool.throwPoolInitializationException(HikariPool.java:596)",
                "error": {"type": "PoolInitializationException"}
            },
        ]
    
    def _mock_error_patterns(self) -> Dict[str, int]:
        """Return realistic mock error pattern counts."""
        logger.info("[MOCK] Generating mock error patterns")
        return {
            "java.lang.OutOfMemoryError": 142,
            "ConnectionPoolTimeoutException": 45,
            "NullPointerException": 12,
            "PoolInitializationException": 8,
            "SocketTimeoutException": 5
        }
