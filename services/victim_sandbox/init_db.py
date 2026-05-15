"""
Project Chimera — Victim Database Initializer
==============================================
Creates the SQLite database schema and seeds it with:
  - users   table (queried by /search and /login — intentionally SQLi-vulnerable)
  - secrets table (contains the flag for the pipeline to capture)
  - products table (legacy, kept for completeness)
Run once before starting the Flask app (handled by entrypoint.sh).
"""

import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "/data/victim.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email    TEXT,
    role     TEXT DEFAULT 'user',
    password TEXT
);

CREATE TABLE IF NOT EXISTS secrets (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    price       REAL NOT NULL
);
"""

SEED_USERS = [
    ("admin", "admin@chimera.local", "admin",  "admin_pass_123"),
    ("alice", "alice@chimera.local",  "user",   "alice_pass_456"),
    ("bob",   "bob@chimera.local",    "user",   "bob_pass_789"),
]

# Override with CTF_FLAG env var so the value is not hardcoded in source control.
_FLAG_VALUE = os.environ.get("CTF_FLAG", "CHIMERA{sql_injection_exploited_patch_me_now}")
SEED_SECRETS = [
    ("flag", _FLAG_VALUE),
]

SEED_PRODUCTS = [
    ("MacBook Pro 16\"", "Apple M3 Pro chip, 18GB RAM.", 2499.99),
    ("Dell XPS 15",      "Intel Core i9, 32GB RAM.",     1899.99),
    ("iPhone 15 Pro",    "A17 Pro chip, 256GB.",          1199.99),
]


def init_db():
    print(f"[init_db] Initializing database at: {DB_PATH}")
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create all tables
    cursor.executescript(SCHEMA)
    print("[init_db] Schema created (users, secrets, products).")

    # Seed users if empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO users (username, email, role, password) VALUES (?, ?, ?, ?)",
            SEED_USERS
        )
        print(f"[init_db] Seeded {len(SEED_USERS)} users.")

    # Seed secrets (flag) if empty
    cursor.execute("SELECT COUNT(*) FROM secrets")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO secrets (key, value) VALUES (?, ?)",
            SEED_SECRETS
        )
        print("[init_db] Seeded flag into secrets table.")

    # Seed products if empty
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
            SEED_PRODUCTS
        )
        print(f"[init_db] Seeded {len(SEED_PRODUCTS)} products.")

    conn.commit()
    conn.close()
    print("[init_db] Done. Database is ready.")


if __name__ == "__main__":
    init_db()

