FROM python:3.11-slim

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create logs directory
RUN mkdir -p /app/logs

# Expose Flask port
EXPOSE 5000

# Initialize DB then start Flask (debug=True allows auto-reload on patching)
CMD ["sh", "-c", "python init_db.py && flask run --host=0.0.0.0 --port=5000 --debug"]
