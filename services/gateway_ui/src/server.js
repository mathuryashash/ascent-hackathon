const express = require('express');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const WebSocket = require('ws');

const app = express();
const server = http.createServer(app);
const PORT = process.env.PORT || 3000;
const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || 'http://orchestrator:8000';
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || 'chimera-demo-secret-2026-hackathon';

// ── WebSocket Proxy ──────────────────────────────────────────────────────────
// Proxy frontend WebSocket connections (on port 3000/3002) to the backend
// orchestrator (on port 8000 inside Docker).
const wss = new WebSocket.Server({ noServer: true });

server.on('upgrade', (request, socket, head) => {
  const pathname = new URL(request.url, `http://${request.headers.host}`).pathname;

  if (pathname === '/ws') {
    // Connect to the backend orchestrator
    const backendWsUrl = ORCHESTRATOR_URL.replace(/^http/, 'ws') + '/ws';
    const backendWs = new WebSocket(backendWsUrl);

    backendWs.on('open', () => {
      wss.handleUpgrade(request, socket, head, (ws) => {
        // Forward messages from frontend to backend
        ws.on('message', (msg) => {
          if (backendWs.readyState === WebSocket.OPEN) backendWs.send(msg);
        });
        // Forward messages from backend to frontend
        backendWs.on('message', (msg) => {
          if (ws.readyState === WebSocket.OPEN) ws.send(msg);
        });
        
        ws.on('close', () => backendWs.close());
        backendWs.on('close', () => ws.close());
        ws.on('error', () => backendWs.close());
        backendWs.on('error', () => ws.close());
      });
    });

    backendWs.on('error', (err) => {
      console.error('Backend WS connection failed:', err.message);
      socket.destroy();
    });
  } else {
    socket.destroy();
  }
});

// ── CORS — allow the static dashboard ────────────────────────────────────────
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
  next();
});

// ── Static files ─────────────────────────────────────────────────────────────
app.use(express.static(path.join(__dirname, '..', 'public')));

app.use(express.json());

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

// ── API Proxy ─────────────────────────────────────────────────────────────────

// Special: Health Check
app.get('/api/health', async (req, res) => {
  try {
    const resp = await orchestratorFetch('/health');
    res.status(resp.status).json(await resp.json());
  } catch (err) {
    res.status(502).json({ status: 'unreachable', detail: err.message });
  }
});

// Special: Trigger (Simulates a signed SIEM alert)
app.post('/api/trigger', async (req, res) => {
  if (!WEBHOOK_SECRET) {
    return res.status(503).json({ error: 'WEBHOOK_SECRET not configured on gateway' });
  }

  const { target, htb_questions } = req.body;
  const alert = {
    type: 'external_recon',
    target: target || 'chimera-victim-1',
    timestamp: new Date().toISOString(),
    evidence: `Manual trigger against ${target || 'internal victim'} from Chimera Dashboard`,
    source: 'gateway-ui-manual',
    htb_questions: htb_questions || '',
    trigger: {
      matched_pattern: 'MANUAL_TRIGGER',
      route: '/manual'
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
      return res.status(resp.status).json({ error: errBody });
    }

    const data = await resp.json();
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: 'Orchestrator unreachable', detail: err.message });
  }
});

// Generic Proxy for all other /api requests
app.all('/api/*', async (req, res) => {
  const orchestratorPath = req.path.replace(/^\/api/, '');
  try {
    const options = {
      method: req.method,
      headers: {},
    };

    if (req.headers['authorization']) {
      options.headers['Authorization'] = req.headers['authorization'];
    }

    if (['POST', 'PUT', 'PATCH'].includes(req.method)) {
      options.body = JSON.stringify(req.body);
    }

    const resp = await orchestratorFetch(orchestratorPath, options);
    const data = await resp.json();
    res.status(resp.status).json(data);
  } catch (err) {
    res.status(502).json({ error: 'Proxy error', detail: err.message });
  }
});

// ── Catch-all: serve index.html ──────────────────────────────────────────────
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '..', 'public', 'index.html'));
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Chimera Gateway UI started on port ${PORT}`);
  console.log(`Proxying API and WebSockets to Orchestrator at ${ORCHESTRATOR_URL}`);
});
