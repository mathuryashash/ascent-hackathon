FROM python:3.11-slim

RUN useradd --system --uid 1001 --no-create-home appuser \
 && apt-get update \
 && apt-get install -y --no-install-recommends sqlite3 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py schema.sql entrypoint.sh ./
RUN chmod +x entrypoint.sh

RUN mkdir -p /data /app/logs && chown -R appuser:appuser /data /app/logs
RUN mkdir -p /home/appuser && chown appuser:appuser /home/appuser

USER appuser

EXPOSE 5000

ENTRYPOINT ["sh", "./entrypoint.sh"]
