FROM python:3.11-slim

# git is required by apply_patch_to_victim (git apply) and uvicorn reload
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all orchestrator source code
COPY . .

EXPOSE 8000

# Start FastAPI with uvicorn (--reload for dev convenience)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
