FROM python:3.11-slim

# Install tools the agents will use from inside the sandbox.
# This runs at BUILD TIME (with internet) — not at runtime (which is network-isolated).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        wget \
        iputils-ping \
        net-tools \
        nmap \
        dnsutils \
        gobuster \
        sqlmap \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for sandboxed command execution
RUN useradd -m -s /bin/bash sandboxuser

WORKDIR /sandbox

# Keep the container alive — orchestrator will exec into it
CMD ["tail", "-f", "/dev/null"]
