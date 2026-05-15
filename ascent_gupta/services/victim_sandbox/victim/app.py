import sqlite3
import logging
import os
import sys
from flask import Flask, request, jsonify

app = Flask(__name__)

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s ACCESS %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "/data/victim.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.before_request
def log_request():
    logger.info(
        "method=%s path=%s qs=%s remote=%s body=%s",
        request.method,
        request.path,
        request.query_string.decode(),
        request.remote_addr,
        request.get_data(as_text=True)[:200],
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "victim"})


@app.route("/search")
def search():
    # -------------------------------------------------------
    # INTENTIONALLY VULNERABLE: raw string formatting → SQLi
    # -------------------------------------------------------
    q = request.args.get("q", "")
    query = f"SELECT id, username, email, role FROM users WHERE username = '{q}'"
    logger.info("QUERY: %s", query)
    try:
        conn = get_db()
        rows = [dict(r) for r in conn.execute(query).fetchall()]
        conn.close()
        return jsonify({"results": rows, "count": len(rows)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/login", methods=["POST"])
def login():
    # -------------------------------------------------------
    # INTENTIONALLY VULNERABLE: raw string formatting → SQLi
    # -------------------------------------------------------
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    query = (
        f"SELECT id, username, role FROM users "
        f"WHERE username = '{username}' AND password = '{password}'"
    )
    logger.info("LOGIN_QUERY: %s", query)
    try:
        conn = get_db()
        row = conn.execute(query).fetchone()
        conn.close()
        if row:
            return jsonify({"success": True, "user": dict(row)})
        return jsonify({"success": False, "message": "Invalid credentials"}), 401
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/users")
def list_users():
    """Non-vulnerable listing endpoint for Architect to read schema."""
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT id, username, email, role FROM users").fetchall()]
    conn.close()
    return jsonify({"users": rows})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
