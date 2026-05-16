import sqlite3, json

conn = sqlite3.connect('/app/checkpoints.sqlite')
conn.row_factory = sqlite3.Row

print("=== Scanning writes for status channel ===")
threads = conn.execute("SELECT DISTINCT thread_id FROM checkpoints").fetchall()

for t in threads:
    tid = t['thread_id']
    writes = conn.execute(
        "SELECT channel, type, value FROM writes WHERE thread_id=? AND channel='status' ORDER BY rowid DESC LIMIT 1",
        (tid,)
    ).fetchall()
    for w in writes:
        try:
            val_raw = w['value']
            val = val_raw.decode('utf-8', errors='replace') if isinstance(val_raw, bytes) else str(val_raw)
            # strip json quotes
            val = val.strip().strip('"')
            if 'approval' in val or 'patch' in val or 'resolv' in val or 'architect' in val:
                print(f"  {tid} | status_raw={repr(val[:60])}")
        except Exception as e:
            print(f"  {tid[:8]} err: {e}")

print("\n=== All latest statuses ===")
for t in threads:
    tid = t['thread_id']
    writes = conn.execute(
        "SELECT channel, value FROM writes WHERE thread_id=? AND channel='status' ORDER BY rowid DESC LIMIT 1",
        (tid,)
    ).fetchone()
    if writes:
        try:
            v = writes['value']
            v = v.decode('utf-8','replace') if isinstance(v, bytes) else str(v)
            v = v.strip().strip('"')
            print(f"  {tid[:8]}... {v}")
        except: pass

conn.close()
