FROM python:3.11-slim

RUN useradd --system --uid 1002 --no-create-home sandboxuser \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        wget \
        nmap \
        iputils-ping \
        netcat-openbsd \
        sqlite3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

RUN pip install --no-cache-dir requests

USER sandboxuser

# Keeps the container alive; orchestrator uses `docker exec` to run payloads
CMD ["sleep", "infinity"]
