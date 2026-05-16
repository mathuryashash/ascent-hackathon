FROM python:3.11-slim

# git is required by apply_patch_to_victim (git apply) and uvicorn reload
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements from its specific path
COPY services/brain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the orchestrator source code and the AI logic needed
COPY services/brain/ .
COPY ascent_gupta/member_2_ai/ ./member_2_ai/

EXPOSE 8000

# Start FastAPI with uvicorn — using shell form to allow $PORT expansion
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
