"""Alert fingerprinting for deduplication."""

import hashlib
import time


def compute_fingerprint(alert_payload: dict) -> str:
    """Stable hash of (service, alert_type, severity, hour_bucket).

    Same alert within the same calendar hour returns the same fingerprint.
    """
    hour_bucket = int(time.time()) // 3600
    key = "|".join([
        alert_payload.get("service", "unknown"),
        alert_payload.get("alert_type", "generic"),
        alert_payload.get("severity", "P3"),
        str(hour_bucket),
    ])
    return hashlib.sha256(key.encode()).hexdigest()
