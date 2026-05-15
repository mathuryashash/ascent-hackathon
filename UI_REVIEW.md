# Project Chimera — UI/UX Audit
**Audited:** 2026-05-15
**Scope:** services/gateway_ui/public/ (4 HTML pages) + services/gateway_ui/src/server.js
**Method:** Static code analysis (no dev server running at audit time)

---

## CRITICAL UX ISSUES

### 1. The /trigger attack simulation has NO UI button — the server feature is completely dark
**Severity: BLOCKER**

`server.js` exposes `POST /trigger` which fires a signed SQLi demo attack, registers the `trace_id`, and starts the SSE stream — the single most important CTF demo action. Zero pages call it. No button, no `fetch('/trigger')`, no `EventSource('/events/:traceId')` anywhere in the frontend. The `/runs`, `/api/approve/:traceId`, and `/api/reject/:traceId` endpoints are equally orphaned.

What this means for a CTF demo: a judge cannot drive the attack from the browser. The entire agentic response loop is invisible at the UI layer. The SSE stream (`/events/:traceId`) exists on the server but the frontend never subscribes to it — instead every page independently opens a WebSocket to either `ws://localhost:8000/ws` or `ws://localhost:3000/ws`. There is no guarantee either target has a `/ws` handler.

**Fix:** Add a "Fire Demo Attack" button to `index.html` that calls `fetch('/trigger', { method: 'POST' })`, reads the returned `trace_id`, and opens an `EventSource('/events/' + traceId)` to drive all real-time UI updates. Wire approve/reject buttons to `/api/approve/:traceId` and `/api/reject/:traceId`.

---

### 2. WebSocket endpoints are hardcoded and inconsistent across pages
**Severity: BLOCKER**

| Page | Hardcoded WS target |
|------|---------------------|
| index.html (line 631) | `ws://localhost:8000/ws` |
| orchestration.html (line 470) | `ws://localhost:8000/ws` |
| auth.html (line 366) | `ws://localhost:3000/ws` |
| observability.html (line 366) | `ws://localhost:3000/ws` |

The gateway runs on port 3000 and proxies to an orchestrator on port 8000. Port 8000 is the Python brain service — it likely has no `/ws` WebSocket handler based on the FastAPI routes in `main.py` (all REST). `index.html` and `orchestration.html` are silently failing. Even the pages targeting port 3000 will fail because `server.js` never registers a WebSocket upgrade handler — it is a plain Express app with no `ws` or `socket.io` dependency.

**Fix:** Either add a `ws` package to `server.js` and proxy WS frames to the brain, or switch all pages to use the SSE endpoint instead. Derive the host from `window.location` rather than hardcoding `localhost`.

---

### 3. No mobile navigation — the sidebar is hidden on small screens with no fallback
**Severity: BLOCKER (for any non-desktop viewer)**

`<aside class="hidden md:flex ...">` — the sidebar is invisible on viewports below 768px. There is no hamburger toggle, no bottom navigation, no drawer. The nav links (`index.html`, `orchestration.html`, etc.) are unreachable on mobile. The body is `overflow-hidden` meaning the user cannot even scroll to find a hidden menu.

**Fix:** Add a hamburger button (`<button aria-label="Open menu">`) in the top bar that is shown only below `md:`, toggling a slide-in drawer or converting to a bottom tab bar.

---

### 4. Two pages are identical — auth.html and observability.html are the same file
**Severity: BLOCKER (dead feature)**

`auth.html` (423 lines) and `observability.html` (423 lines) are byte-for-byte the same content: the same "hero stats" section with hardcoded `99.98%`, the same "Active Pipelines" and "Agent Fleet" layout, the same WebSocket script pointing to `ws://localhost:3000/ws`. The navigation in auth.html even marks itself as active on the "Auth Portal" item, while observability.html marks "Observability". Neither page provides the feature its name implies. An "Auth Portal" for a CTF platform should show token management or HMAC key config; "Observability" should show Prometheus/metrics data. Currently both show copy-pasted hero stats with static numbers.

**Fix:** Replace auth.html with token/secret management UI (show/rotate `WEBHOOK_SECRET`, display current runs). Replace observability.html with a live `/api/metrics` Prometheus scrape view using a `<pre>` block or Chart.js time-series fed from `/api/metrics`.

---

## DESIGN IMPROVEMENTS

### 5. Hardcoded metric values across three pages give false operational confidence
`auth.html`, `observability.html`, and the hero-stats inside those pages display `99.98%` uptime, `42ms` latency, `1.2M/h` tokens, and `100%` webhook success as static HTML strings — not values fetched from `/api/health` or `/api/metrics`. In a CTF demo environment where the orchestrator may be down, these values will confidently display "All services operational" regardless of actual state. This is actively misleading.

**Fix:** On page load, call `fetch('/api/health')` and update all four stat cards from the response. If the orchestrator is unreachable (502), show an error state card with a red indicator instead of green.

---

### 6. Pipeline node visualization does not clear state between runs
`index.html` pipeline nodes get CSS classes `active`, `completed`, or `failed` added via `updatePipelineNode()` but the function only removes those three classes — it never resets the `border-color` or `box-shadow` inline styles that may have been added by previous state. More importantly, on reconnect after a disconnect, the prior node states remain visually "completed" from the previous run, with no way to know if they represent the current execution.

**Fix:** Add a `resetPipeline()` function called when `alert_received` fires. Clear all node classes, reset metric counters to zero, and flush the timeline and activity-stream divs with a `[New run started]` marker.

---

### 7. The "Deploy Agent" button and sidebar "Security" / "Support" links are all dead
Three sidebar items have `href="#"`: Security, Support. The "Deploy Agent" button (sidebar footer) has no `onclick`, no `href`, and no associated form. "RESTART ALL AGENTS" on auth/observability pages similarly has no handler. In a CTF demo, judges click things. Dead UI reads as incomplete.

**Fix:** Either wire buttons to real actions (`fetch('/api/health')` for agent status check, `/api/approve` etc.) or remove them. If they are future-roadmap items, mark them visually disabled with `opacity-50 cursor-not-allowed` and a tooltip.

---

### 8. Success Rate stat card on index.html never receives data
`index.html` shows a "Success Rate" card (line 285-292) with `id="success-rate"` initialized to `--`. The `updateMetrics()` function (line 550-558) only updates `current-status` and `iteration-count`. Nothing ever writes to `success-rate`. The card will show `--` for the entire lifetime of a run. Same applies to `avg-response` (line 266) and `response-trend` (line 269).

**Fix:** Compute success rate from `APP_STATE.resolvedIncidents / APP_STATE.totalIncidents` and update on each `pipeline_complete` event. Compute avg response time from `Date.now() - startTime` on completion and write to `avg-response`.

---

### 9. Orchestration page timer uses requestAnimationFrame on an unbounded loop
`orchestration.html` line 415-419: `updateTimerDisplay()` calls `requestAnimationFrame(updateTimerDisplay)` with no termination condition. It starts on `alert_received` but never stops — not on `pipeline_complete`, not on tab visibility change, not on page unload. Over a long CTF session this is a guaranteed frame-rate drain. No `cancelAnimationFrame` handle is stored.

**Fix:** Store the handle: `STATE.rafHandle = requestAnimationFrame(updateTimerDisplay)`. Cancel with `cancelAnimationFrame(STATE.rafHandle)` on `pipeline_complete` and in a `document.addEventListener('visibilitychange', ...)` guard.

---

### 10. Page titles are missing — all four pages have no `<title>` tag
None of the four HTML files have a `<title>` element. Browser tab shows a blank title. For a CTF platform being judged with multiple browser tabs open, this makes tab identification impossible.

**Fix:** Add descriptive titles: `<title>Chimera Dashboard</title>`, `<title>Chimera Orchestration</title>`, etc.

---

## MISSING FEATURES

### 11. No "Trigger Attack" UI — the most important CTF interaction is absent
Described in detail under Critical Issue #1. The `POST /trigger` endpoint builds a signed SQLi payload and registers a `trace_id`, but there is no button, feedback, or run-tracking UI. A CTF judge needs to press one button, see the attack fire, watch the 7-node pipeline light up in real time, and see the flag captured. That full loop is architecturally present on the server but entirely absent in the UI.

---

### 12. No run history panel — /runs endpoint is never consumed
`server.js` provides `GET /runs` which returns the last 20 `trace_id` entries with status. Nothing in the frontend fetches or displays this. For a CTF scenario where multiple attacks are fired in sequence, there is no way to review prior runs, re-inspect a captured flag, or jump to a specific trace.

**Fix:** Add a collapsible "Run History" panel to `index.html` that polls `GET /runs` on load and after each completed pipeline. Each row should show `trace_id`, `status`, `startTime`, and a "View" button that re-subscribes to `GET /api/status/:traceId`.

---

### 13. No SIEM alert inspector panel
When an alert arrives via webhook, the raw payload (type, target, evidence, timestamp) is never shown to the user. The Ingress node on the pipeline diagram lights up but the user cannot see what triggered it. In a CTF scenario this is the attack evidence — the "flag-adjacent" data that explains why the AI responded.

**Fix:** Add an "Incoming Alert" panel below the metric cards that shows the deserialized webhook payload when `alert_received` fires. Include: attack type badge, target service, raw evidence string in a `<code>` block, and timestamp.

---

### 14. No approve / reject UI for human-in-the-loop mode
`server.js` exposes `POST /api/approve/:traceId` and `POST /api/reject/:traceId`. These suggest a HITL (human-in-the-loop) confirmation mode — one of the strongest CTF demo moments. No page renders approve/reject buttons. When a run is in a state requiring human approval, the operator has no browser-visible affordance to act.

**Fix:** In the "Current Execution State" panel on `index.html`, add conditional approve/reject buttons that appear when `data.status === 'awaiting_approval'`, each calling the respective API endpoint.

---

### 15. No threat severity indicator or attack classification display
The CTF scenario involves SQL injection but the UI uses generic terms ("Current Status: IDLE"). There is no severity badge (Critical/High/Medium), no CVE or CWE reference display, no MITRE ATT&CK tactic mapping, and no visual distinction between attack types. A security dashboard for a CTF audience should speak security vocabulary.

**Fix:** Map `alert.type` values to severity levels and colors. Display a severity badge (e.g., "CRITICAL — SQLi") using the `error` color token (`#ffb4ab`) on the status card when an attack is active.

---

### 16. Chart.js is imported on index.html and orchestration.html but never used
Both pages load Chart.js 3.9.1 from cdnjs. No `<canvas>` element, no `new Chart(...)` call appears anywhere. This is a dead 200KB+ network dependency on every page load.

**Fix:** Remove the Chart.js `<script>` tag from any page that does not use it. If time-series charting is planned (response time over iterations), add a canvas and initialize a line chart fed by `APP_STATE.responseTimes`.

---

## WHAT WORKS WELL

**Visual design language is cohesive and appropriate for a CTF/security tool.** The dark navy background (`#0b1326`), cyan primary (`#c3f5ff`/`#00daf3`), and green-mint tertiary (`#a8ffd2`) form a credible hacking aesthetic. Glass-panel cards with `backdrop-filter: blur(12px)`, subtle `rgba(255,255,255,0.1)` borders, and glow effects (`shadow-[0_0_8px_#a8ffd2]`) feel polished for a hackathon context.

**Typography system is well-structured.** The combination of Geist (display/headlines), Inter (body), and JetBrains Mono (code blocks) is exactly right for a security platform. The custom font size scale with specific `lineHeight` and `letterSpacing` values shows deliberate typographic thinking.

**Pipeline node visualization on index.html is conceptually strong.** The 7-node horizontal flow (Ingress → Scout → Summarize → Investigate → Architect → Verify) with CSS class-based state switching (`active`, `completed`, `failed`), pulse-ring animation, and color-coded borders (`#00daf3` active, `#a8ffd2` completed, `#ffb4ab` failed) is exactly the right pattern for this tool. The underlying JS state machine (`APP_STATE.nodeStates`) and `updatePipelineNode()` function are cleanly written.

**Diff viewer is correctly implemented.** `displayPatch()` in `index.html` splits a unified diff by newline, identifies `+`/`-` lines by prefix, and applies `diff-add`/`diff-remove`/`diff-neutral` CSS classes correctly. This is the most CTF-relevant display component and it works as written.

**Orchestration timeline page is the best single page.** It maps each pipeline node to a dedicated timeline card with hypothesis, exploit proof, captured flag, and patch data fields — all driven from WebSocket events. The execution timer, iteration counter, and performance metrics section are correctly wired to state updates. The `formatDuration()` / `formatTime()` utilities handle edge cases.

**Activity stream message cap is correctly implemented.** The 50-message limit in `addStreamMessage()` (index.html line 529-532) prevents unbounded DOM growth during long-running CTF scenarios.

**Server-side SSE implementation is solid.** `server.js` `/events/:traceId` polls the orchestrator every 2 seconds, writes typed SSE events (`event: state`, `event: error`), correctly terminates the stream on `resolved`/`failed` status, and cleans up the interval on client disconnect. The 500ms final-flush delay before `res.end()` is a thoughtful edge-case handle.

**HMAC webhook signing is correctly implemented.** `server.js` uses `crypto.createHmac('sha256', WEBHOOK_SECRET)` to sign the demo alert payload before POST — this is the correct pattern for a CTF system where the brain service validates signatures.

---

## FILES AUDITED

- `services/gateway_ui/src/server.js` (227 lines)
- `services/gateway_ui/package.json`
- `services/gateway_ui/public/index.html` (715 lines) — main CTF dashboard
- `services/gateway_ui/public/orchestration.html` (512 lines) — pipeline timeline
- `services/gateway_ui/public/auth.html` (422 lines) — duplicate of observability
- `services/gateway_ui/public/observability.html` (422 lines) — duplicate of auth
