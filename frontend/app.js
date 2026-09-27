// Samadhan citizen chat — T21. Talks only to POST /api/v1/message (S01 contract).
// No business logic here: every action/reply comes from the backend as-is.

// Point this at the mock (T08) today; switch to :8000 once T18 ships the real /message route.
const API_BASE = 'http://localhost:8001';

const chatEl = document.getElementById('chat');
const composerEl = document.getElementById('composer');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('btn-send');
const restartBtn = document.getElementById('btn-restart');
const cancelBtn = document.getElementById('btn-cancel');

const SESSION_KEY = 'samadhan_session_id';

function getSessionId() {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function appendMessage(role, text) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  el.textContent = text;
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

function appendSummaryCard(botMsgEl, summary) {
  const card = document.createElement('div');
  card.className = 'card card-summary';
  const title = document.createElement('div');
  title.className = 'card-title';
  title.textContent = 'जाँच करें:';
  const dl = document.createElement('dl');
  for (const [key, value] of Object.entries(summary || {})) {
    const dt = document.createElement('dt');
    dt.textContent = key;
    const dd = document.createElement('dd');
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  card.appendChild(title);
  card.appendChild(dl);
  botMsgEl.appendChild(card);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function appendTicketCard(botMsgEl, ticket) {
  const card = document.createElement('div');
  card.className = 'card card-ticket';
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
  chatEl.scrollTop = chatEl.scrollHeight;
}

function setBusy(busy) {
  inputEl.disabled = busy;
  sendBtn.disabled = busy;
  restartBtn.disabled = busy;
  cancelBtn.disabled = busy;
}

async function sendToApi(text) {
  const form = new FormData();
  form.append('session_id', getSessionId());
  form.append('message_id', crypto.randomUUID());
  form.append('text', text);

  const response = await fetch(`${API_BASE}/api/v1/message`, {
    method: 'POST',
    body: form,
  });

  const body = await response.json();
  if (!response.ok) {
    // S01 section 7: every non-2xx body carries a citizen-safe reply_text.
    throw new Error(body.reply_text || 'कुछ गड़बड़ हो गई। कृपया दोबारा प्रयास करें।');
  }
  return body;
}

async function send(text) {
  const trimmed = text.trim();
  if (!trimmed) return;

  appendMessage('citizen', trimmed);
  setBusy(true);

  try {
    const result = await sendToApi(trimmed);
    const botEl = appendMessage('bot', result.reply_text);
    if (result.action === 'confirm' && result.summary) {
      appendSummaryCard(botEl, result.summary);
    }
    if (result.action === 'submitted' && result.ticket) {
      appendTicketCard(botEl, result.ticket);
    }
  } catch (err) {
    appendMessage('error', err.message || 'सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।');
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

composerEl.addEventListener('submit', (event) => {
  event.preventDefault();
  const text = inputEl.value;
  inputEl.value = '';
  inputEl.style.height = 'auto';
  send(text);
});

inputEl.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    composerEl.requestSubmit();
  }
});

inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 120)}px`;
});

restartBtn.addEventListener('click', () => send('restart'));
cancelBtn.addEventListener('click', () => send('cancel'));

// Hero's "Start Conversation" — scrolls to the chat below and hands off focus.
const heroCta = document.getElementById('hero-cta');
const appShell = document.getElementById('app');
if (heroCta && appShell) {
  heroCta.addEventListener('click', () => {
    appShell.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTimeout(() => inputEl.focus(), 500);
  });
}

appendMessage('bot', 'नमस्ते! अपनी पानी की समस्या यहाँ लिखिए।');
