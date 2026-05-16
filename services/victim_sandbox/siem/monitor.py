"""
SIEM Simulator — monitors victim container logs via Docker SDK.
When a SQL injection pattern is detected it fires a HMAC-signed
webhook POST to the orchestrator's /webhook/alert endpoint.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone

import docker
import requests

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [SIEM] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://orchestrator:8000/webhook/alert")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "changeme")
VICTIM_CONTAINER = os.getenv("VICTIM_CONTAINER", "chimera-victim-1")

if WEBHOOK_SECRET == "changeme":
    raise RuntimeError(
        "WEBHOOK_SECRET must be set to a strong secret in the environment. "
        "The default value 'changeme' is not permitted in any environment."
    )
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))

# Patterns that indicate SQLi attempt in the victim's access logs
SQLI_PATTERNS = [
    re.compile(r"' OR '?1'?='?1", re.IGNORECASE),
    re.compile(r"'\s*OR\s+1\s*=\s*1", re.IGNORECASE),
    re.compile(r"UNION\s+SELECT", re.IGNORECASE),
    re.compile(r"';\s*(DROP|DELETE|UPDATE|INSERT)\s+", re.IGNORECASE),
    re.compile(r"--\s*$"),
    re.compile(r"' OR '"),
    re.compile(r"1=1"),
    re.compile(r"'\s*;"),
    re.compile(r"SLEEP\s*\(", re.IGNORECASE),
    re.compile(r"BENCHMARK\s*\(", re.IGNORECASE),
]


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def fire_webhook(alert_type: str, evidence: str, target: str = "victim-service") -> None:
    payload = {
        "type": alert_type,
        "target": target,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evidence": evidence[:500],
    }
    body = json.dumps(payload).encode()
    sig = _sign(body)
    try:
        resp = requests.post(
            WEBHOOK_URL,
            data=body,
            headers={"Content-Type": "application/json", "X-Webhook-Signature": f"sha256={sig}"},
            timeout=10,
        )
        log.info("Webhook fired → HTTP %s", resp.status_code)
    except requests.exceptions.RequestException as exc:
        log.warning("Webhook delivery failed: %s", exc)


def classify_line(line: str) -> str | None:
    # URL-decode to catch patterns like %20UNION%20SELECT
    decoded_line = urllib.parse.unquote(line)
    for pat in SQLI_PATTERNS:
        if pat.search(decoded_line):
            return "sqli"
    return None


def monitor() -> None:
    client = docker.from_env()
    log.info("Monitoring container '%s' for attack patterns…", VICTIM_CONTAINER)

    seen: set[str] = set()

    while True:
        try:
            container = client.containers.get(VICTIM_CONTAINER)
            raw = container.logs(tail=100, timestamps=True).decode("utf-8", errors="replace")

            for line in raw.splitlines():
                alert_type = classify_line(line)
                if alert_type and line not in seen:
                    log.warning("DETECTED %s → %s", alert_type.upper(), line[:120])
                    fire_webhook(alert_type, line)
                    seen.add(line)
                    # Bound the dedup set to avoid unbounded memory growth
                    if len(seen) > 2000:
                        seen = set(list(seen)[-1000:])

        except docker.errors.NotFound:
            log.error("Container '%s' not found — waiting for it to start…", VICTIM_CONTAINER)
        except docker.errors.APIError as exc:
            log.error("Docker API error: %s", exc)
        except Exception as exc:
            log.error("Unexpected error: %s", exc)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    monitor()
