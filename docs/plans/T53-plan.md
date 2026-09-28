# Plan: T53 — Floating chat widget (real, text-only, for pages without the full chat)

Ticket: `docs/TICKETS.md` T53 (new, owner D, depends on S01/S15 — both `[x]`, done when "Real
widget open/closes, sends/receives real messages on status.html"). Spec:
`docs/specs/S19-chat-widget.md`.

**Scope: T53 only.** A new, self-mounting `frontend/widget.js`, shared CSS additions to
`frontend/style.css` (reuses existing `.msg`/`.card`/`.input`/`.send-btn` classes rather than a
new visual language), and one `<script>` include added to `frontend/status.html`. Text-only, real
backend. `index.html`, `backend/`, and `dashboard/` untouched.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `frontend/widget.js` | Create | Self-mounting floating widget: DOM, open/close, real `POST /api/v1/message` text turns |
| `frontend/style.css` | Edit | Widget positioning/panel/button styles, reusing existing bubble/card/form classes |
| `frontend/status.html` | Edit | One `<script src="widget.js">` include |
| `docs/TICKETS.md` | Edit | Add T53 row; tick `[x]` once verified |

## 2. Steps, in order

**S1 — `frontend/widget.js`.** Self-mounting IIFE, builds its own DOM (`#samadhan-widget-root`
containing a discoverability label, the toggle button, and the panel), no HTML placeholder needed
on the host page. Reuses `app.js`'s exact `session_id`/`message_id`/`FormData` shape and the same
`sessionStorage` key (D-S19-1) so a conversation continues across entry points in one tab. Reuses
`.input`/`.send-btn`/`.msg`/`.card`/`.card-summary`/`.card-ticket`/`.card-ticket-confirm`/`.badge`
classes directly — no new visual language, minimal new CSS. Error handling mirrors `postToApi`
exactly: `fetch()` and `.json()` each in their own `try`/`catch`, `GENERIC_ERROR` fallback, real
`reply_text` shown for actual HTTP errors (same T50-fixed pattern, duplicated per D-S19-2, not
imported — this repo has no module system/build step).

```js
// Samadhan floating chat widget -- T53 (S19). Real backend, text-only. Drop-in: add
// <script src="widget.js"> to any page that also loads style.css. Self-mounting, no HTML
// placeholder needed. No business logic here: every action/reply comes from the backend as-is,
// same posture as app.js. Deliberately does not import from app.js (D-S19-2): no build step/module
// system exists in this project, and the slice of logic needed here is small and stable (S01).

(function () {
  const API_BASE = 'http://localhost:8000';
  const SESSION_KEY = 'samadhan_session_id'; // D-S19-1: same key app.js uses -- same conversation
  const SEEN_KEY = 'samadhan_widget_seen';
  const GENERIC_ERROR = 'सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।';

  function getSessionId() {
    let id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  function svgIcon(pathsD) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '26');
    svg.setAttribute('height', '26');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    for (const d of pathsD) {
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', d);
      svg.appendChild(path);
    }
    return svg;
  }

  const CHAT_PATH = [
    'M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a' +
      '8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z',
  ];
  const CLOSE_PATH = ['M18 6L6 18', 'M6 6l12 12'];

  const root = document.createElement('div');
  root.id = 'samadhan-widget-root';

  const label = document.createElement('div');
  label.id = 'samadhan-widget-label';
  label.textContent = '💬 सहायता चाहिए? · Need help?';

  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.id = 'samadhan-widget-toggle';
  toggleBtn.setAttribute('aria-label', 'समाधान से बात करें');
  toggleBtn.appendChild(svgIcon(CHAT_PATH));

  const panel = document.createElement('div');
  panel.id = 'samadhan-widget-panel';
  panel.hidden = true;

  const header = document.createElement('div');
  header.id = 'samadhan-widget-header';
  const title = document.createElement('span');
  title.textContent = 'समाधान';
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.id = 'samadhan-widget-close';
  closeBtn.setAttribute('aria-label', 'बंद करें');
  closeBtn.appendChild(svgIcon(CLOSE_PATH));
  header.appendChild(title);
  header.appendChild(closeBtn);

  const messagesEl = document.createElement('div');
  messagesEl.id = 'samadhan-widget-messages';
  messagesEl.setAttribute('aria-live', 'polite');

  const composer = document.createElement('form');
  composer.id = 'samadhan-widget-composer';
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'input'; // reuse existing form styles, no new visual language
  input.placeholder = 'यहाँ लिखें…';
  input.required = true;
  input.autocomplete = 'off';
  const sendBtn = document.createElement('button');
  sendBtn.type = 'submit';
  sendBtn.className = 'send-btn';
  sendBtn.textContent = 'भेजें';
  composer.appendChild(input);
  composer.appendChild(sendBtn);

  panel.appendChild(header);
  panel.appendChild(messagesEl);
  panel.appendChild(composer);
  root.appendChild(label);
  root.appendChild(panel);
  root.appendChild(toggleBtn);
  document.body.appendChild(root);

  function appendMessage(role, text) {
    const el = document.createElement('div');
    el.className = `msg ${role} msg-in`;
    el.textContent = text;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  function appendSummaryCard(botMsgEl, summary) {
    const card = document.createElement('div');
    card.className = 'card card-summary';
    const cardTitle = document.createElement('div');
    cardTitle.className = 'card-title';
    cardTitle.textContent = 'जाँच करें:';
    const dl = document.createElement('dl');
    for (const [key, value] of Object.entries(summary || {})) {
      const dt = document.createElement('dt');
      dt.textContent = key;
      const dd = document.createElement('dd');
      dd.textContent = value;
      dl.appendChild(dt);
      dl.appendChild(dd);
    }
    card.appendChild(cardTitle);
    card.appendChild(dl);
    botMsgEl.appendChild(card);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function appendTicketCard(botMsgEl, ticket) {
    const card = document.createElement('div');
    card.className = 'card card-ticket card-ticket-confirm';
    const id = document.createElement('div');
    id.className = 'complaint-id';
    id.textContent = ticket.complaint_id;
    const dept = document.createElement('div');
    dept.className = 'ticket-row';
    dept.textContent = `विभाग: ${ticket.department}`;
    const office = document.createElement('div');
    office.className = 'ticket-row';
    office.textContent = `कार्यालय: ${ticket.office.name}`;
    card.appendChild(id);
    card.appendChild(dept);
    card.appendChild(office);
    if (ticket.status === 'needs_review') {
      const badge = document.createElement('div');
      badge.className = 'badge';
      badge.textContent = 'समीक्षा के लिए भेजा गया';
      card.appendChild(badge);
    }
    botMsgEl.appendChild(card);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function setBusy(busy) {
    input.disabled = busy;
    sendBtn.disabled = busy;
  }

  async function postToApi(text) {
    const form = new FormData();
    form.append('session_id', getSessionId());
    form.append('message_id', crypto.randomUUID());
    form.append('text', text);

    let response;
    try {
      response = await fetch(`${API_BASE}/api/v1/message`, { method: 'POST', body: form });
    } catch {
      throw new Error(GENERIC_ERROR);
    }
    let body;
    try {
      body = await response.json();
    } catch {
      throw new Error(GENERIC_ERROR);
    }
    if (!response.ok) {
      throw new Error(body.reply_text || GENERIC_ERROR);
    }
    return body;
  }

  async function send(text) {
    const trimmed = text.trim();
    if (!trimmed) return;
    appendMessage('citizen', trimmed);
    setBusy(true);
    try {
      const result = await postToApi(trimmed);
      const botEl = appendMessage('bot', result.reply_text);
      if (result.action === 'confirm' && result.summary) appendSummaryCard(botEl, result.summary);
      if (result.action === 'submitted' && result.ticket) appendTicketCard(botEl, result.ticket);
    } catch (err) {
      appendMessage('error', err.message || GENERIC_ERROR);
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  composer.addEventListener('submit', (event) => {
    event.preventDefault();
    const text = input.value;
    input.value = '';
    send(text);
  });

  let opened = false;
  let greeted = false;

  function setOpen(open) {
    opened = open;
    panel.hidden = !open;
    root.classList.toggle('samadhan-widget-open', open);
    toggleBtn.textContent = '';
    toggleBtn.appendChild(svgIcon(open ? CLOSE_PATH : CHAT_PATH));
    toggleBtn.setAttribute('aria-label', open ? 'बंद करें' : 'समाधान से बात करें');
    if (open) {
      label.hidden = true;
      sessionStorage.setItem(SEEN_KEY, '1');
      if (!greeted) {
        greeted = true;
        appendMessage('bot', 'नमस्ते! मैं समाधान हूँ। अपना सवाल यहाँ लिखिए।');
      }
      input.focus();
    }
  }

  toggleBtn.addEventListener('click', () => setOpen(!opened));
  closeBtn.addEventListener('click', () => setOpen(false));

  if (sessionStorage.getItem(SEEN_KEY)) {
    label.hidden = true; // D-S19-3: shown once per browser session only
  }
})();
```

**S2 — `frontend/style.css` additions** (appended as their own labelled block, same convention as
the Status-check and Hero sections already in the file):
```css
/* ---------------------------------------------------------------------------
   Floating chat widget (T53) -- reuses .msg/.card/.input/.send-btn styles above.
--------------------------------------------------------------------------- */

#samadhan-widget-root {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 1000;
  display: flex;
  align-items: flex-end;
  gap: 10px;
}

#samadhan-widget-label {
  background: var(--header-bg);
  color: var(--header-text);
  font-size: 13px;
  padding: 8px 14px;
  border-radius: 999px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2);
  white-space: nowrap;
  margin-bottom: 8px;
}

#samadhan-widget-toggle {
  order: 2;
  flex: none;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  border: none;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.4);
  animation: widget-idle-pulse 3s ease-in-out infinite;
}

@keyframes widget-idle-pulse {
  0%, 100% { box-shadow: 0 8px 24px rgba(37, 99, 235, 0.4), 0 0 0 0 rgba(37, 99, 235, 0.3); }
  50% { box-shadow: 0 8px 24px rgba(37, 99, 235, 0.4), 0 0 0 10px rgba(37, 99, 235, 0); }
}

#samadhan-widget-panel {
  position: fixed;
  right: 20px;
  bottom: 92px;
  width: min(360px, calc(100vw - 40px));
  height: min(520px, calc(100vh - 140px));
  background: var(--bg);
  border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transform-origin: bottom right;
  animation: widget-panel-in 0.22s ease-out;
}

#samadhan-widget-panel[hidden] {
  display: none;
}

@keyframes widget-panel-in {
  from { opacity: 0; transform: scale(0.9) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

#samadhan-widget-header {
  flex: none;
  background: var(--header-bg);
  color: var(--header-text);
  padding: 14px 16px;
  font-weight: 700;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

#samadhan-widget-close {
  background: transparent;
  border: none;
  color: var(--header-text);
  cursor: pointer;
  display: flex;
  padding: 4px;
}

#samadhan-widget-messages {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

#samadhan-widget-composer {
  flex: none;
  border-top: 1px solid var(--bot-border);
  background: var(--bot-bg);
  padding: 10px;
  display: flex;
  gap: 8px;
}

#samadhan-widget-composer .input {
  min-height: 44px;
}

@media (max-width: 420px) {
  #samadhan-widget-root { right: 12px; bottom: 12px; }
  #samadhan-widget-panel { right: 12px; bottom: 84px; }
}

@media (prefers-reduced-motion: reduce) {
  #samadhan-widget-toggle { animation: none; }
  #samadhan-widget-panel { animation: none; }
}
```

**S3 — `frontend/status.html`**: add `<script src="widget.js"></script>` right after the existing
`<script src="status.js"></script>` line. No other change to that file.

## 3. Acceptance coverage

| S19 acceptance item | Satisfied by | Verified by |
|---|---|---|
| Floating button, bottom-right, on `status.html` | S1 DOM + S2 CSS | Verification step 1 |
| Open/close animation | S2 `widget-panel-in` keyframe + icon swap | Verification step 1 |
| Modern chat interface, consistent with the site | S2 reuses `.msg`/`.card` classes | Visual check |
| Real user/AI messages | S1 `postToApi`/`send` — real `POST /api/v1/message` | Verification step 2 |
| No raw browser/JS error shown | S1's `GENERIC_ERROR` pattern, identical to T50's fix | Verification step 3 |

## 4. New libraries
None. Plain DOM APIs, no build step.

## 5. How this doesn't regress T21/T29/T51/T52/T22
- `frontend/app.js`/`index.html` untouched entirely — the full-page chat is unaffected.
- `frontend/status.js` untouched — the widget's DOM is fully namespaced (`#samadhan-widget-*`),
  runs in its own IIFE scope, and never reads/writes anything `status.js` owns.
- `style.css` additions are a new, clearly labelled block; no existing selector's rules are edited.
- `backend/`, `dashboard/` untouched.

## Verification
1. `cd backend; uv run uvicorn app.main:app --port 8000` (real `.env`) + `cd frontend; python -m
   http.server 5500`. Open `status.html`: confirm the floating button + label appear bottom-right,
   click opens the panel with a visible animation and a short Hindi greeting, click again (or ×)
   closes it. Confirm the label disappears after first open and stays gone on subsequent opens in
   the same tab (`sessionStorage`).
2. Send a real message in the widget (e.g. "3 din se pani nahi aa raha") — confirm a real reply
   renders from the real backend, continue the conversation through to a real `submitted` ticket.
3. Stop the backend mid-conversation, send another message — confirm the Hindi `GENERIC_ERROR`
   fallback renders, not a raw browser error (same check as every other ticket that touches
   `fetch()` in this repo).
4. Confirm `status.html`'s own existing status-lookup form still works unchanged alongside the
   widget (no collision, no regression).
5. Open `index.html` and confirm it is completely unaffected (no widget present — by design, not
   included there).

## Not doing in this turn
- Voice, GPS, or TTS in the widget (S19 OUT OF SCOPE) — text-only, by explicit scope decision.
- Adding the widget to `index.html` or the dashboard.
- Any backend change.
- Automated frontend tests — no test framework exists in `frontend/` (same posture as every prior
  frontend ticket in this project); relies on the manual Verification above.

## Revision (same day): full feature parity with app.js

Direct instruction: "make the floating widget fully equivalent to the existing full-page chatbot
in terms of functionality and behavior." `widget.js` was rewritten (still self-mounting, still no
imports from `app.js` — D-S19-2) to mirror `app.js` in full:

- Composer restructured to reuse `.composer`/`.composer-actions`/`.voice-row`/`.composer-row`
  directly — same DOM shape as `index.html`'s composer, just namespaced under
  `#samadhan-widget-composer`, so no new visual language was needed, only two small scoped CSS
  overrides (tighter padding, `flex-wrap` on the chip row for the narrower 400px panel).
- Added: press-and-hold recording (`beginHold`/`endHold`/`MIN_HOLD_MS`/mic states, identical logic
  to `app.js`'s S18 implementation, including the guarded `setPointerCapture` fix from G-S18-4),
  GPS location with `ask_for`-highlight, TTS speak buttons on every bot bubble, restart/cancel
  chips, and the delayed bilingual auto-play greeting (typing indicator → 3s → greeting card →
  best-effort Hindi autoplay → tap-to-listen fallback on autoplay block).
- Panel grown 360×520 → 400×620 to fit the fuller composer without cramping.

**Live-verified against the real backend, same session**: mic icon renders correctly (custom SVG
path, not copy-pasted markup); full press-and-hold → real upload → real ASR round trip → correct
empty-transcript handling with a 🔊 button on the reply; GPS location sends and a real reply
renders; restart/cancel commands work (`"आपकी शिकायत रद्द कर दी गई है।"`); the bilingual greeting
renders and its autoplay/fallback behaves identically to the full page's; no console errors; no
collision with `status.html`'s own lookup form, re-checked again after the rewrite.

`docs/TICKETS.md` T53 stays `[x]` — its own done-when ("real widget opens/closes, sends/receives
real messages") was already true before this revision and remains true; this revision expands
*what* it can send/receive, not whether the ticket's original bar was met.
