"""
Project Chimera — Victim Database Initializer
==============================================
Creates the SQLite database schema and seeds it with sample products.
Run once before starting the Flask app.
"""

import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "/app/database.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    price       REAL NOT NULL
);
"""

SEED_DATA = [
    ("MacBook Pro Laptop 16\"", "Apple M3 Pro chip, 18GB RAM, 512GB SSD. Professional-grade laptop.", 2499.99),
    ("Dell XPS Laptop 15",      "Intel Core i9, 32GB RAM, 1TB NVMe SSD. Ultra-thin premium laptop.",  1899.99),
    ("iPhone 15 Pro",           "A17 Pro chip, 256GB, Titanium frame, ProRes video recording.",        1199.99),
    ("Samsung Galaxy S24",      "Snapdragon 8 Gen 3, 12GB RAM, 256GB, 200MP camera.",                  999.99),
    ("Sony WH-1000XM5",         "Industry-leading noise cancellation, 30-hour battery life.",           349.99),
    ("iPad Pro 12.9\"",         "M2 chip, Liquid Retina XDR display, 256GB WiFi + Cellular.",         1299.99),
    ("Logitech MX Master 3",    "Advanced wireless mouse with MagSpeed scroll and ergonomic design.",    99.99),
    ("LG 27\" 4K Monitor",      "IPS panel, USB-C, HDR400, 60Hz refresh rate, slim bezel design.",     599.99),
    ("Razer BlackWidow V3",     "Mechanical gaming keyboard with Razer Green switches and RGB.",        139.99),
    ("Anker 65W USB-C Hub",     "7-in-1 USB-C hub: HDMI, USB-A, SD card, PD charging.",               49.99),
]


def init_db():
    print(f"[init_db] Initializing database at: {DB_PATH}")
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create schema
    cursor.executescript(SCHEMA)
    print("[init_db] Schema created.")

    # Seed only if table is empty
    cursor.execute("SELECT COUNT(*) FROM products")
    count = cursor.fetchone()[0]

    if count == 0:
        cursor.executemany(
            "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
            SEED_DATA
        )
        conn.commit()
        print(f"[init_db] Seeded {len(SEED_DATA)} products.")
    else:
        print(f"[init_db] Database already has {count} products. Skipping seed.")

    conn.close()
    print("[init_db] Done. Database is ready.")


if __name__ == "__main__":
    init_db()
