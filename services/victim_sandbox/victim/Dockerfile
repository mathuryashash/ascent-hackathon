FROM python:3.11-slim

RUN useradd --system --uid 1001 --no-create-home appuser \
 && apt-get update \
 && apt-get install -y --no-install-recommends sqlite3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py schema.sql entrypoint.sh ./
RUN chmod +x entrypoint.sh

RUN mkdir -p /data && chown appuser:appuser /data

USER appuser

EXPOSE 5000

ENTRYPOINT ["./entrypoint.sh"]
