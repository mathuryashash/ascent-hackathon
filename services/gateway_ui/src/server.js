'use strict';
/**
 * server.js — Chimera Gateway UI
 *
 * Responsibilities:
 *   - Serve the React dashboard from public/
 *   - Proxy API calls to the orchestrator (avoiding browser CORS)
 *   - SSE endpoint: poll orchestrator state and push to browser in real time
 *   - POST /trigger: sign and fire a demo SQLi alert at the orchestrator
 *   - GET /runs: in-memory registry of known trace_ids
 */

const express = require('express');
const path = require('path');
const crypto = require('crypto');

const app = express();
const PORT = parseInt(process.env.PORT || '3000');
const ORCHESTRATOR_URL = (process.env.ORCHESTRATOR_URL || 'http://localhost:8000').replace(/\/$/, '');
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || '';

// In-memory run registry: trace_id → { trace_id, status, startTime, triggered }
const runRegistry = new Map();

app.use(express.json());

// ── CORS — allow the static dashboard (opened from file:// or any origin) ─────
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', req.headers.origin || '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type,Authorization');
  if (req.method === 'OPTIONS') { res.sendStatus(200); return; }
  next();
});

// ── Security headers ──────────────────────────────────────────────────────────
app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'SAMEORIGIN');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  // Allow ws://localhost:8001 for direct orchestrator WebSocket from dashboard pages
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:; connect-src 'self' ws: wss: http://localhost:8001 http://localhost:3001 http://localhost:5000;");
  next();
});

// ── Static files ─────────────────────────────────────────────────────────────
app.use(express.static(path.join(__dirname, '..', 'public')));

// ── Utility ──────────────────────────────────────────────────────────────────
async function orchestratorFetch(urlPath, options = {}) {
  const url = `${ORCHESTRATOR_URL}${urlPath}`;
  return fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
}

function log(level, msg, extra = {}) {
  console.log(JSON.stringify({ level, msg, ts: new Date().toISOString(), ...extra }));
}

// ── API Proxy ─────────────────────────────────────────────────────────────────

// GET /api/status/:traceId
app.get('/api/status/:traceId', async (req, res) => {
  try {
    const resp = await orchestratorFetch(`/status/${req.params.traceId}`);
    const data = await resp.json();
    if (runRegistry.has(req.params.traceId)) {
      runRegistry.get(req.params.traceId).status = data.status;
    }
    res.status(resp.status).json(data);
  } catch (err) {
    res.status(502).json({ error: 'Orchestrator unreachable', detail: err.message });
  }
});

// GET /api/metrics
app.get('/api/metrics', async (req, res) => {
  try {
    const resp = await orchestratorFetch('/metrics');
    const text = await resp.text();
    res.status(resp.status).type('text/plain').send(text);
  } catch (err) {
    res.status(502).json({ error: 'Orchestrator unreachable', detail: err.message });
  }
});

// GET /api/health (orchestrator health)
app.get('/api/health', async (req, res) => {
  try {
    const resp = await orchestratorFetch('/health');
    res.status(resp.status).json(await resp.json());
  } catch (err) {
    res.status(502).json({ status: 'unreachable', detail: err.message });
  }
});

// POST /api/approve/:traceId
app.post('/api/approve/:traceId', async (req, res) => {
  try {
    const resp = await orchestratorFetch(`/approve/${req.params.traceId}`, { method: 'POST' });
    res.status(resp.status).json(await resp.json());
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// POST /api/reject/:traceId
app.post('/api/reject/:traceId', async (req, res) => {
  try {
    const resp = await orchestratorFetch(`/reject/${req.params.traceId}`, { method: 'POST' });
    res.status(resp.status).json(await resp.json());
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// GET /api/verify-fix/:traceId
app.get('/api/verify-fix/:traceId', async (req, res) => {
  try {
    const r = await fetch(`${ORCHESTRATOR_URL}/verify-fix/${req.params.traceId}`);
    const data = await r.json();
    res.json(data);
  } catch (e) {
    res.status(502).json({ error: e.message });
  }
});

// ── SSE: real-time run state stream ──────────────────────────────────────────
app.get('/api/events/:traceId', async (req, res) => {
  const { traceId } = req.params;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no'); // disable nginx buffering
  res.flushHeaders();

  const TERMINAL_STATUSES = new Set(['resolved', 'failed', 'rejected']);

  const sendState = async () => {
    try {
      const resp = await orchestratorFetch(`/status/${traceId}`);
      if (!resp.ok) {
        res.write(`event: error\ndata: ${JSON.stringify({ status: resp.status })}\n\n`);
        return false;
      }
      const data = await resp.json();
      res.write(`event: state\ndata: ${JSON.stringify(data)}\n\n`);

      if (runRegistry.has(traceId)) {
        runRegistry.get(traceId).status = data.status;
      }

      return TERMINAL_STATUSES.has(data.status);
    } catch (err) {
      res.write(`event: error\ndata: ${JSON.stringify({ error: err.message })}\n\n`);
      return false;
    }
  };

  // Immediate first push
  const done = await sendState();
  if (done) { res.end(); return; }

  const interval = setInterval(async () => {
    const finished = await sendState();
    if (finished) {
      clearInterval(interval);
      setTimeout(() => res.end(), 500); // final flush delay
    }
  }, 2000);

  req.on('close', () => {
    clearInterval(interval);
    log('info', 'SSE client disconnected', { traceId });
  });
});

// ── POST /api/trigger — fire a signed demo attack ────────────────────────────
app.post('/api/trigger', async (req, res) => {
  if (!WEBHOOK_SECRET) {
    return res.status(503).json({ error: 'WEBHOOK_SECRET not configured on gateway' });
  }

  const alert = {
    type: 'sqli',
    target: 'victim-service',
    timestamp: new Date().toISOString(),
    evidence: "GET /search?q=' OR '1'='1 HTTP/1.1 — triggered from Chimera Dashboard",
    source: 'gateway-ui-demo',
    trigger: {
      matched_pattern: 'UNION SELECT',
      route: '/search'
    }
  };

  const body = JSON.stringify(alert);
  const signature = 'sha256=' + crypto.createHmac('sha256', WEBHOOK_SECRET).update(body).digest('hex');

  try {
    const resp = await orchestratorFetch('/webhook/alert', {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': signature,
      },
    });

    if (!resp.ok) {
      const errBody = await resp.text();
      log('error', 'Trigger rejected by orchestrator', { status: resp.status, body: errBody });
      return res.status(resp.status).json({ error: errBody });
    }

    const data = await resp.json();
    const traceId = data.trace_id;

    runRegistry.set(traceId, {
      trace_id: traceId,
      status: 'starting',
      startTime: Date.now(),
      triggered: true,
    });

    log('info', 'Demo attack triggered', { traceId });
    res.json({ trace_id: traceId, message: 'SQLi attack simulation triggered successfully' });
  } catch (err) {
    log('error', 'Trigger failed', { error: err.message });
    res.status(502).json({ error: 'Orchestrator unreachable', detail: err.message });
  }
});

// ── GET /api/traces — proxy all traces from orchestrator ─────────────────────
app.get('/api/traces', async (req, res) => {
  try {
    const resp = await orchestratorFetch('/traces');
    res.status(resp.status).json(await resp.json());
  } catch (err) {
    res.status(502).json({ error: 'Orchestrator unreachable', detail: err.message });
  }
});

// ── GET /api/runs — list known runs ──────────────────────────────────────────
app.get('/api/runs', (req, res) => {
  const list = Array.from(runRegistry.values())
    .sort((a, b) => b.startTime - a.startTime)
    .slice(0, 20); // last 20 runs
  res.json(list);
});

// ── GET /health — gateway liveness ───────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'chimera-gateway-ui', runs: runRegistry.size });
});

// ── Catch-all: React app ──────────────────────────────────────────────────────
app.get('*', (req, res) => {
  if (req.path.startsWith('/api/')) {
    return res.status(404).json({ error: 'Not found' });
  }
  res.sendFile(path.join(__dirname, '..', 'public', 'index.html'));
});

// ── Start ─────────────────────────────────────────────────────────────────────
app.listen(PORT, '0.0.0.0', () => {
  log('info', 'Chimera Gateway UI started', { port: PORT, orchestrator: ORCHESTRATOR_URL });
});
