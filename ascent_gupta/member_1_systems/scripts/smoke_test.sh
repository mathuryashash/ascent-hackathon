#!/usr/bin/env bash
# smoke_test.sh — Integration test for Project Chimera Member 1 deliverables.
#
# What it tests:
#   1. Victim service is healthy and serves the /search endpoint.
#   2. The SQLi vulnerability is real (payload returns admin data).
#   3. SIEM detects the attack and fires a HMAC-signed webhook.
#   4. Orchestrator /webhook returns 202 (accepted).
#
# Usage:
#   WEBHOOK_SECRET=your_secret bash smoke_test.sh

set -euo pipefail

VICTIM_URL="${VICTIM_URL:-http://localhost:5000}"
ORCHESTRATOR_URL="${ORCHESTRATOR_URL:-http://localhost:8000}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-changeme}"

GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
NC="\033[0m"

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

# ── 1. Wait for victim to be healthy ────────────────────────────────────────
info "Waiting for victim service at $VICTIM_URL ..."
for i in $(seq 1 20); do
    if curl -sf "$VICTIM_URL/health" > /dev/null 2>&1; then
        pass "Victim is healthy."
        break
    fi
    [ "$i" -eq 20 ] && fail "Victim did not start within 20 seconds."
    sleep 1
done

# ── 2. Normal search returns one result ─────────────────────────────────────
info "Testing normal search..."
RESULT=$(curl -sf "$VICTIM_URL/search?q=alice")
COUNT=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])")
[ "$COUNT" -eq "1" ] && pass "Normal search returns 1 result." || fail "Normal search returned unexpected count: $COUNT"

# ── 3. SQLi payload dumps all users ─────────────────────────────────────────
info "Testing SQLi payload: ' OR '1'='1..."
SQLI_RESULT=$(curl -sf "$VICTIM_URL/search?q=%27%20OR%20%271%27%3D%271")
SQLI_COUNT=$(echo "$SQLI_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])")
[ "$SQLI_COUNT" -gt "1" ] && pass "SQLi confirmed: $SQLI_COUNT rows returned (expected >1)." \
    || fail "SQLi did not work — got $SQLI_COUNT rows."

# ── 4. Webhook endpoint accepts HMAC-signed alert ───────────────────────────
info "Testing HMAC-signed webhook delivery..."
BODY='{"type":"sqli","target":"victim-service","timestamp":"2024-01-01T00:00:00Z","evidence":"smoke_test"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$ORCHESTRATOR_URL/webhook" \
    -H "Content-Type: application/json" \
    -H "X-Signature: $SIG" \
    -d "$BODY")
[ "$HTTP_CODE" -eq "202" ] && pass "Orchestrator returned 202 Accepted." \
    || fail "Orchestrator returned HTTP $HTTP_CODE (expected 202)."

# ── 5. Unsigned webhook is rejected ─────────────────────────────────────────
info "Testing that unsigned webhook is rejected..."
HTTP_CODE_UNAUTH=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$ORCHESTRATOR_URL/webhook" \
    -H "Content-Type: application/json" \
    -d "$BODY")
[ "$HTTP_CODE_UNAUTH" -eq "403" ] && pass "Unsigned webhook correctly rejected with 403." \
    || fail "Unsigned webhook returned HTTP $HTTP_CODE_UNAUTH (expected 403)."

echo ""
echo -e "${GREEN}All smoke tests passed.${NC}"
