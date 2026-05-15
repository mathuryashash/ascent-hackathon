"""
Project Chimera — Victim Flask App
====================================
INTENTIONALLY VULNERABLE — For hackathon/educational purposes ONLY.
Contains a raw SQL injection vulnerability on the /search route.
"""

import os
import sqlite3
import datetime
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "/data/victim.db")
LOG_PATH = os.environ.get("LOG_PATH", "/app/logs/access.log")

# ─────────────────────────────────────────────────────────────────────────────
# HTML Template
# ─────────────────────────────────────────────────────────────────────────────

HOME_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chimera Shop — Product Search</title>
    <style>
        body { font-family: sans-serif; max-width: 700px; margin: 60px auto; background: #f0f2f5; }
        h1 { color: #c0392b; }
        form { display: flex; gap: 8px; margin: 20px 0; }
        input[type=text] { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px; }
        button { padding: 10px 20px; background: #c0392b; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
        .note { background: #ffeaa7; padding: 10px; border-radius: 4px; font-size: 12px; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>🛒 Chimera Shop</h1>
    <p>Search our product catalogue below:</p>
    <form action="/search" method="GET">
        <input type="text" name="q" placeholder="Search products..." id="search-input">
        <button type="submit" id="search-btn">Search</button>
    </form>
    <div class="note">
        ⚠️ <strong>HACKATHON DEMO:</strong> This application is intentionally vulnerable to SQL Injection.
    </div>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Logging Helper
# ─────────────────────────────────────────────────────────────────────────────

def log_request(query: str, status: int) -> None:
    """Appends a structured log line to the access.log file."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    method = request.method
    path = request.full_path if request.query_string else request.path
    log_line = f"[{timestamp}] {method} {path} | status={status}\n"
    try:
        with open(LOG_PATH, "a") as f:
            f.write(log_line)
    except Exception as e:
        app.logger.error(f"Failed to write log: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Database Helper
# ─────────────────────────────────────────────────────────────────────────────

def get_db():
    """Returns a SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Homepage with search form."""
    return render_template_string(HOME_HTML)


@app.route("/search")
def search():
    """
    ⚠️  INTENTIONALLY VULNERABLE TO SQL INJECTION ⚠️
    Uses raw string interpolation — NOT parameterized queries.
    This is by design for Project Chimera's autonomous exploit demo.
    """
    query = request.args.get("q", "")
    status_code = 200

    try:
        conn = get_db()
        cursor = conn.cursor()

        # 🚨 VULNERABLE: raw string interpolation
        sql = f"SELECT id, name, description, price FROM products WHERE name LIKE '%{query}%'"
        app.logger.info(f"Executing SQL: {sql}")
        cursor.execute(sql)

        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()

        response = {
            "status": "ok",
            "query": query,
            "count": len(results),
            "results": results
        }

    except sqlite3.OperationalError as e:
        status_code = 500
        response = {
            "status": "error",
            "query": query,
            "error": str(e),
            "sqlite3.OperationalError": True
        }
    except Exception as e:
        status_code = 500
        response = {"status": "error", "message": str(e)}

    log_request(query, status_code)
    return jsonify(response), status_code


@app.route("/health")
def health():
    """Health check endpoint used by Docker and the Orchestrator."""
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    status = "ok" if db_ok else "degraded"
    http_status = 200 if db_ok else 503
    return jsonify({"status": status, "db": db_ok}), http_status


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # use_reloader=True enables auto-reload when apply_patch_to_victim writes new source;
    # debug=False disables the Werkzeug interactive debugger (arbitrary RCE via /__debugger__)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=True)
