const express = require('express');
const path = require('path');
const http = require('http');
const WebSocket = require('ws');

const app = express();
const port = 3000;

app.use(express.static(path.join(__dirname, '../public')));

const server = http.createServer(app);
const wss = new WebSocket.Server({ server, path: '/ws' });

wss.on('connection', (ws) => {
  console.log('Client connected to mock WebSocket');
  
  // Initial message
  ws.send(JSON.stringify({ type: 'system', content: 'Connection established. Awaiting SIEM payload...' }));

  // Simulate an attack sequence after a delay
  setTimeout(() => {
    ws.send(JSON.stringify({ type: 'system', content: 'SIEM Alert Received: SQL Injection detected from 192.168.1.45' }));
    
    setTimeout(() => {
      ws.send(JSON.stringify({ type: 'thought', content: 'Analyzing SQL injection payload: \' OR \'1\'=\'1' }));
    }, 2000);

    setTimeout(() => {
      ws.send(JSON.stringify({ type: 'thought', content: 'Payload attempts to bypass authentication. Exploiting vulnerability to confirm...' }));
    }, 4000);

    setTimeout(() => {
      ws.send(JSON.stringify({ type: 'tool_call', tool: 'execute_bash_sandboxed', content: 'Testing exploit on sandboxed instance...' }));
    }, 6000);

    setTimeout(() => {
      ws.send(JSON.stringify({ type: 'tool_result', content: 'Exploit successful. Admin access achieved. Vulnerability confirmed.' }));
    }, 8500);

    setTimeout(() => {
      ws.send(JSON.stringify({ type: 'thought', content: 'Generating patch for app.py to use parameterized queries instead of string concatenation.' }));
    }, 11000);
    
    setTimeout(() => {
      ws.send(JSON.stringify({ type: 'system', content: 'Patch deployed to staging. Verifier agent initiating test suite.' }));
    }, 14000);
    
  }, 5000);
});

server.listen(port, () => {
  console.log(`Gateway UI listening at http://localhost:${port}`);
});
