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
      // fetch() itself throws on a network/CORS/offline failure with the browser's own English
      // message -- never let that reach the citizen; always show GENERIC_ERROR (T50).
      throw new Error(GENERIC_ERROR);
    }
    let body;
    try {
      body = await response.json();
    } catch {
      throw new Error(GENERIC_ERROR);
    }
    if (!response.ok) {
      // S01 section 7: every non-2xx body carries a citizen-safe reply_text.
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
