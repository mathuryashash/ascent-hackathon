#!/bin/sh
set -e

DB_PATH="${DB_PATH:-/data/victim.db}"

if [ ! -f "$DB_PATH" ]; then
    echo "[victim] Initialising database at $DB_PATH..."
    sqlite3 "$DB_PATH" < /app/schema.sql
    echo "[victim] Database ready."
fi

exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    app:app
