FROM python:3.11-slim

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create logs directory (SIEM tails this)
RUN mkdir -p /app/logs

EXPOSE 5000

# Initialize DB then start Flask (debug=True allows auto-reload after patching)
CMD ["sh", "-c", "python init_db.py && flask run --host=0.0.0.0 --port=5000 --debug"]
