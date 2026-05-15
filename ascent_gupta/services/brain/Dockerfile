FROM python:3.11-slim

WORKDIR /app

# Install git for the Architect to run git apply
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy brain requirements
COPY services/brain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the member_2_ai package so the brain can import it
COPY member_2_ai /app/member_2_ai
COPY member_1_systems /app/member_1_systems

# Copy the brain app itself
COPY services/brain /app/services/brain

ENV PYTHONPATH=/app

# Run the FastAPI server
CMD ["uvicorn", "services.brain.main:app", "--host", "0.0.0.0", "--port", "8000"]
