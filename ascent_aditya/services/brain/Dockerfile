FROM python:3.11-slim

WORKDIR /app

# Member 2 will add their LangGraph dependencies here
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all orchestrator source code
COPY . .

EXPOSE 8000

# Start FastAPI with uvicorn (--reload for dev convenience)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
