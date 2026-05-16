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
from flask_cors import CORS


app = Flask(__name__)
CORS(app)


DB_PATH = os.environ.get("DB_PATH", "/app/database.db")
LOG_PATH = os.environ.get("LOG_PATH", "/app/logs/access.log")

# ?????????????????????????????????????????????????????????????????????????????
# HTML Templates
# ?????????????????????????????????????????????????????????????????????????????

LOGIN_HTML = """
<!DOCTYPE html><html><head><title>Login - Chimera Tech</title>
<style>body{font-family:sans-serif;background:#0b1326;color:#dae2fd;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
.box{background:#171f33;border:1px solid #3b494c;padding:40px;border-radius:8px;width:320px}
h2{color:#00daf3;margin-top:0}input{width:100%;padding:8px;margin:8px 0 16px;background:#0b1326;border:1px solid #3b494c;color:#dae2fd;border-radius:4px;box-sizing:border-box}
button{width:100%;padding:10px;background:#006875;color:#fff;border:none;border-radius:4px;cursor:pointer}
.error{color:#ffb4ab;margin-bottom:12px;font-size:14px}</style></head>
<body><div class="box"><h2>🔒 Staff Login</h2>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
<form method="POST"><input name="username" placeholder="Username" required/><input name="password" type="password" placeholder="Password" required/>
<button type="submit">Login</button></form>
<p style="font-size:12px;color:#849396;margin-top:16px">Hint: Try <code>' OR '1'='1</code></p></div></body></html>
"""

LOGIN_SUCCESS_HTML = """
<!DOCTYPE html><html><head><title>Welcome - Chimera Tech</title>
<style>body{font-family:sans-serif;background:#0b1326;color:#dae2fd;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
.box{background:#171f33;border:1px solid #a8ffd2;padding:40px;border-radius:8px;width:320px;text-align:center}
h2{color:#a8ffd2}</style></head>
<body><div class="box"><h2>✅ Access Granted</h2>
<p>Welcome, <strong>{{ username }}</strong>!</p>
<p style="color:#849396;font-size:13px">Auth bypass successful via SQL injection.</p>
<a href="/" style="color:#00daf3">← Back to Shop</a></div></body></html>
"""

HOME_HTML = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chimera Tech | Premium Electronics</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #09090b;
            --bg-surface: #18181b;
            --bg-surface-hover: #27272a;
            --border: rgba(255, 255, 255, 0.1);
            --text-primary: #fafafa;
            --text-secondary: #a1a1aa;
            --accent: #3b82f6;
            --danger: #ef4444;
            --danger-bg: rgba(239, 68, 68, 0.1);
            --gradient-brand: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg-base);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at top left, rgba(59, 130, 246, 0.15), transparent 40%),
                radial-gradient(circle at bottom right, rgba(139, 92, 246, 0.15), transparent 40%);
        }

        /* Nav & Hero */
        header {
            width: 100%;
            max-width: 1200px;
            padding: 60px 20px 40px;
            text-align: center;
            animation: fadeInDown 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }

        .brand-badge {
            display: inline-block;
            padding: 6px 12px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border);
            border-radius: 100px;
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-secondary);
            margin-bottom: 24px;
            backdrop-filter: blur(10px);
        }

        h1 {
            font-size: clamp(3rem, 5vw, 4.5rem);
            font-weight: 700;
            letter-spacing: -0.04em;
            line-height: 1.1;
            margin-bottom: 16px;
            background: linear-gradient(to right, #fff, #a1a1aa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        h1 span {
            background: var(--gradient-brand);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .hero-desc {
            font-size: 1.25rem;
            color: var(--text-secondary);
            max-width: 600px;
            margin: 0 auto;
            line-height: 1.6;
            font-weight: 400;
        }

        /* Search Interface */
        .search-wrapper {
            width: 100%;
            max-width: 640px;
            padding: 0 20px;
            position: relative;
            z-index: 10;
            margin-bottom: 40px;
            animation: fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards 0.2s;
            opacity: 0;
            transform: translateY(20px);
        }

        .search-box {
            position: relative;
            display: flex;
            align-items: center;
            background: rgba(24, 24, 27, 0.6);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 8px;
            backdrop-filter: blur(20px);
            box-shadow: 0 4px 24px -1px rgba(0, 0, 0, 0.2);
            transition: all 0.3s ease;
        }

        .search-box:focus-within {
            border-color: rgba(59, 130, 246, 0.5);
            box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1), 0 10px 40px -10px rgba(0, 0, 0, 0.5);
            background: rgba(24, 24, 27, 0.9);
        }

        .search-icon {
            padding: 0 16px;
            color: var(--text-secondary);
        }

        .search-input {
            flex: 1;
            background: transparent;
            border: none;
            color: var(--text-primary);
            font-size: 1.125rem;
            font-family: inherit;
            padding: 12px 0;
            outline: none;
        }

        .search-input::placeholder { color: #52525b; }

        .search-btn {
            background: var(--text-primary);
            color: var(--bg-base);
            border: none;
            border-radius: 10px;
            padding: 12px 24px;
            font-weight: 600;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .search-btn:hover {
            transform: scale(1.02);
            background: #e4e4e7;
        }

        .search-btn:active { transform: scale(0.98); }

        /* Grid & Cards */
        .grid-container {
            width: 100%;
            max-width: 1200px;
            padding: 0 20px 80px;
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 24px;
        }

        .product-card {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
            opacity: 0;
            transform: translateY(20px);
            animation: cardEnter 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .product-card:hover {
            transform: translateY(-4px);
            border-color: rgba(255, 255, 255, 0.2);
            box-shadow: 0 20px 40px -12px rgba(0,0,0,0.5);
            background: var(--bg-surface-hover);
        }

        .product-title {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 8px;
            letter-spacing: -0.01em;
        }

        .product-desc {
            color: var(--text-secondary);
            font-size: 0.95rem;
            line-height: 1.6;
            margin-bottom: 24px;
            flex-grow: 1;
        }

        .product-meta {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-top: 16px;
            border-top: 1px solid var(--border);
        }

        .product-price {
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }

        .product-id {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: #52525b;
            background: #000;
            padding: 4px 8px;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.05);
        }

        /* Hacked State (Glitch) */
        .card-hacked {
            border-color: var(--danger);
            background: rgba(15, 5, 5, 0.8);
            box-shadow: 0 0 30px rgba(239, 68, 68, 0.15) inset;
        }
        
        .card-hacked .product-title {
            color: var(--danger);
            font-family: 'JetBrains Mono', monospace;
            animation: glitch 1s linear infinite;
        }

        .card-hacked .product-desc {
            font-family: 'JetBrains Mono', monospace;
            color: #fca5a5;
            font-size: 0.85rem;
            background: rgba(0,0,0,0.5);
            padding: 12px;
            border-radius: 8px;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        /* Status & Loaders */
        .status-text {
            width: 100%;
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.95rem;
            margin-bottom: 24px;
            height: 20px;
        }

        .skeleton {
            background: linear-gradient(90deg, #18181b 25%, #27272a 50%, #18181b 75%);
            background-size: 200% 100%;
            animation: loading 1.5s infinite;
            border-radius: 4px;
        }

        /* Animations */
        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes cardEnter {
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes loading {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
        @keyframes glitch {
            2%, 64% { transform: translate(2px,0) skew(0deg); }
            4%, 60% { transform: translate(-2px,0) skew(0deg); }
            62% { transform: translate(0,0) skew(5deg); }
        }

        /* Security Banner */
        .sec-banner {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(9, 9, 11, 0.9);
            border: 1px solid var(--border);
            padding: 10px 20px;
            border-radius: 100px;
            font-size: 0.8rem;
            color: var(--text-secondary);
            backdrop-filter: blur(10px);
            z-index: 100;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .sec-banner .dot {
            width: 8px; height: 8px;
            background: var(--danger);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--danger);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.4; }
            100% { opacity: 1; }
        }
    </style>
</head>
<body>

    <header>
        <div class="brand-badge">Chimera v2.0</div>
        <h1>Next-Gen <span>Hardware</span></h1>
        <p class="hero-desc">Experience the future of computing. Search our curated catalog of ultra-premium electronics and accessories.</p>
    </header>

    <div class="search-wrapper">
        <form class="search-box" onsubmit="handleSearch(event)">
            <svg class="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input type="text" id="searchInput" class="search-input" placeholder="Search products (e.g., laptop, monitor)..." autocomplete="off">
            <button type="submit" class="search-btn">Search</button>
        </form>
    </div>

    <div id="statusText" class="status-text"></div>
    <div id="grid" class="grid-container"></div>

    <div class="sec-banner">
        <div class="dot"></div>
        <span>Hackathon Target Environment - Vulnerable to SQLi</span>
    </div>

    <script>
        window.onload = () => fetchResults('');

        async function handleSearch(e) {
            e.preventDefault();
            const q = document.getElementById('searchInput').value;
            await fetchResults(q);
        }

        function showSkeletons() {
            const grid = document.getElementById('grid');
            grid.innerHTML = Array(6).fill().map(() => `
                <div class="product-card" style="animation: none; opacity: 1; transform: none;">
                    <div class="skeleton" style="height: 24px; width: 70%; margin-bottom: 12px;"></div>
                    <div class="skeleton" style="height: 16px; width: 100%; margin-bottom: 8px;"></div>
                    <div class="skeleton" style="height: 16px; width: 80%; margin-bottom: 24px;"></div>
                    <div style="margin-top: auto; display: flex; justify-content: space-between;">
                        <div class="skeleton" style="height: 28px; width: 30%;"></div>
                        <div class="skeleton" style="height: 20px; width: 20%;"></div>
                    </div>
                </div>
            `).join('');
        }

        async function fetchResults(query) {
            const grid = document.getElementById('grid');
            const status = document.getElementById('statusText');
            
            status.textContent = 'Searching database...';
            showSkeletons();
            
            try {
                // Fetch from the vulnerable backend
                const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();
                
                grid.innerHTML = ''; 

                if (data.status === 'error') {
                    status.innerHTML = `<span style="color: var(--danger)">Database Error Occurred</span>`;
                    const errDiv = document.createElement('div');
                    errDiv.style.cssText = 'grid-column: 1/-1; text-align: center; color: var(--danger); padding: 40px; font-family: monospace; background: rgba(239,68,68,0.1); border-radius: 12px;';
                    errDiv.textContent = data.error || data.message;
                    grid.appendChild(errDiv);
                    return;
                }

                if (data.results && data.results.length > 0) {
                    status.textContent = `Found ${data.count} result(s)`;

                    data.results.forEach((product, i) => {
                        // Detect injected anomalous rows (SQLi payload success)
                        const isHacked = !product.description || typeof product.price !== 'number';
                        const delay = i * 0.05; // Staggered entry

                        const card = document.createElement('div');
                        card.className = `product-card ${isHacked ? 'card-hacked' : ''}`;
                        card.style.animationDelay = `${delay}s`;

                        if (isHacked) {
                            // Use textContent for all user-data fields to prevent stored XSS
                            const title = document.createElement('div');
                            title.className = 'product-title';
                            title.textContent = 'SYSTEM_COMPROMISED';

                            const desc = document.createElement('div');
                            desc.className = 'product-desc';
                            desc.innerHTML = '> DATA LEAK DETECTED<br>> PAYLOAD EXECUTION SUCCESS<br><br>';
                            const pre = document.createElement('pre');
                            pre.style.display = 'inline';
                            pre.textContent = JSON.stringify(product, null, 2);
                            desc.appendChild(pre);

                            const meta = document.createElement('div');
                            meta.className = 'product-meta';
                            const price = document.createElement('span');
                            price.className = 'product-price';
                            price.style.color = 'var(--danger)';
                            price.textContent = 'NULL';
                            const pid = document.createElement('span');
                            pid.className = 'product-id';
                            pid.textContent = `ERR_ID_${product.id || 'X'}`;
                            meta.appendChild(price);
                            meta.appendChild(pid);

                            card.appendChild(title);
                            card.appendChild(desc);
                            card.appendChild(meta);
                        } else {
                            // Use textContent to prevent stored XSS from DB values
                            const title = document.createElement('div');
                            title.className = 'product-title';
                            title.textContent = product.name;

                            const desc = document.createElement('div');
                            desc.className = 'product-desc';
                            desc.textContent = product.description;

                            const meta = document.createElement('div');
                            meta.className = 'product-meta';
                            const price = document.createElement('span');
                            price.className = 'product-price';
                            price.textContent = `$${product.price.toFixed(2)}`;
                            const pid = document.createElement('span');
                            pid.className = 'product-id';
                            pid.textContent = `UID_${product.id.toString().padStart(4, '0')}`;
                            meta.appendChild(price);
                            meta.appendChild(pid);

                            card.appendChild(title);
                            card.appendChild(desc);
                            card.appendChild(meta);
                        }
                        grid.appendChild(card);
                    });
                } else {
                    status.textContent = 'No products found.';
                }
            } catch (err) {
                status.innerHTML = `<span style="color: var(--danger)">Network Connection Failed</span>`;
                grid.innerHTML = '';
            }
        }
    </script>
</body>
</html>
"""

# ?????????????????????????????????????????????????????????????????????????????
# Logging Helper
# ?????????????????????????????????????????????????????????????????????????????

def log_request(query: str, status: int) -> None:
    """Appends a structured log line to the access.log file."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        method = request.method
        path = request.full_path if request.query_string else request.path

        log_line = f"[{timestamp}] {method} {path} | status={status}\n"
        with open(LOG_PATH, "a") as f:
            f.write(log_line)
    except Exception as e:
        # Non-fatal: just print to stdout
        print(f"ERROR in app: Failed to write log: {e}")


# ?????????????????????????????????????????????????????????????????????????????
# Database Helper
# ?????????????????????????????????????????????????????????????????????????????

def get_db():
    """Returns a SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ?????????????????????????????????????????????????????????????????????????????
# Routes
# ?????????????????????????????????????????????????????????????????????????????

@app.route("/")
def index():
    """Homepage with search form."""
    return render_template_string(HOME_HTML)


@app.route("/search")
def search():
    """
    ??  INTENTIONALLY VULNERABLE TO SQL INJECTION ??
    Uses raw string interpolation ? NOT parameterized queries.
    This is by design for Project Chimera's autonomous exploit demo.
    """
    query = request.args.get("q", "")
    status_code = 200

    try:
        conn = get_db()
        cursor = conn.cursor()

        # ?? VULNERABLE: raw string interpolation
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


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Intentionally vulnerable login — demonstrates auth bypass via SQLi."""
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        # INTENTIONALLY VULNERABLE: raw string interpolation
        query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
        try:
            conn = get_db()
            cur = conn.execute(query)
            user = cur.fetchone()
            conn.close()
        except Exception as e:
            error = f"DB error: {e}"
            user = None
        if user:
            return render_template_string(LOGIN_SUCCESS_HTML, username=user[0] if user else username)
        else:
            error = error or "Invalid credentials"
    return render_template_string(LOGIN_HTML, error=error)


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
    return jsonify({"status": status, "db": db_ok}), 200


# ?????????????????????????????????????????????????????????????????????????????
# Entry Point
# ?????????????????????????????????????????????????????????????????????????????

if __name__ == "__main__":
    # debug=True enables auto-reload when apply_patch_to_victim writes new source
    app.run(host="0.0.0.0", port=5000, debug=True)
