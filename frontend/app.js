// Samadhan citizen chat — T21. Talks only to POST /api/v1/message (S01 contract).
// No business logic here: every action/reply comes from the backend as-is.

// Real backend (T18 shipped the real /message route; matches status.js's API_BASE, S15 G-S15-1).
const API_BASE = 'http://localhost:8000';

const chatEl = document.getElementById('chat');
const composerEl = document.getElementById('composer');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('btn-send');
const restartBtn = document.getElementById('btn-restart');
const cancelBtn = document.getElementById('btn-cancel');
const micBtn = document.getElementById('btn-mic');
const locationBtn = document.getElementById('btn-location');

const SESSION_KEY = 'samadhan_session_id';
const GENERIC_ERROR = 'सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।';
const ACCEPTED_AUDIO_TYPES = new Set(['audio/webm', 'audio/ogg', 'audio/mp4', 'audio/wav']); // S01 4.1

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
  micBtn.disabled = busy;
  locationBtn.disabled = busy;
}

function normaliseAudioType(mimeType) {
  // 'audio/webm;codecs=opus' -> 'audio/webm' -- mirrors app.schemas.normalise_content_type.
  return (mimeType || '').split(';', 1)[0].trim().toLowerCase();
}

async function postToApi(buildForm) {
  const form = new FormData();
  form.append('session_id', getSessionId());
  form.append('message_id', crypto.randomUUID());
  buildForm(form);

  let response;
  try {
    response = await fetch(`${API_BASE}/api/v1/message`, { method: 'POST', body: form });
  } catch {
    // fetch() itself throws on a network/CORS/offline failure with the browser's own English
    // message -- never let that reach the citizen; always show GENERIC_ERROR.
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

function setLocationHighlight(on) {
  locationBtn.classList.toggle('chip-btn-highlight', on);
}

async function handleTurn(apiCall, citizenBubbleText) {
  const citizenEl = appendMessage('citizen', citizenBubbleText);
  setBusy(true);

  try {
    const result = await apiCall();
    if (result.transcript) {
      citizenEl.textContent = result.transcript; // S16 D-S16-3: show what was actually heard
    }
    setLocationHighlight(result.ask_for === 'location'); // S16 D-S16-1 / S01 D-A4
    const botEl = appendMessage('bot', result.reply_text);
    if (result.action === 'confirm' && result.summary) {
      appendSummaryCard(botEl, result.summary);
    }
    if (result.action === 'submitted' && result.ticket) {
      appendTicketCard(botEl, result.ticket);
    }
  } catch (err) {
    appendMessage('error', err.message || GENERIC_ERROR);
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

async function send(text) {
  const trimmed = text.trim();
  if (!trimmed) return;
  await handleTurn(() => postToApi((form) => form.append('text', trimmed)), trimmed);
}

// --- S16: recording -----------------------------------------------------------------------

let mediaRecorder = null;
let recordedChunks = [];

function setRecordingUI(recording) {
  micBtn.classList.toggle('mic-btn-recording', recording);
  const label = recording ? 'रिकॉर्डिंग बंद करें' : 'आवाज़ रिकॉर्ड करें';
  micBtn.setAttribute('aria-label', label);
  micBtn.title = label;
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) {
    appendMessage('error', 'यह ब्राउज़र आवाज़ रिकॉर्ड नहीं कर सकता। कृपया लिखकर भेजें।');
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    appendMessage('error', 'माइक्रोफ़ोन का उपयोग नहीं हो सका। कृपया अनुमति दें या लिखकर भेजें।');
    return;
  }

  recordedChunks = [];
  mediaRecorder = new MediaRecorder(stream); // S16 D-S16-2: no explicit mimeType, browser default
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) recordedChunks.push(event.data);
  };
  mediaRecorder.onstop = () => {
    stream.getTracks().forEach((track) => track.stop()); // S16 RULES 5: release the mic indicator
    void sendRecording(mediaRecorder.mimeType);
  };
  mediaRecorder.start();
  setRecordingUI(true);
}

async function sendRecording(mimeType) {
  const type = normaliseAudioType(mimeType);
  if (!ACCEPTED_AUDIO_TYPES.has(type)) {
    appendMessage('error', 'यह ऑडियो प्रारूप समर्थित नहीं है। कृपया लिखकर भेजें।');
    setRecordingUI(false);
    return;
  }
  const blob = new Blob(recordedChunks, { type });
  setRecordingUI(false);
  await handleTurn(
    () => postToApi((form) => form.append('audio', blob, `recording.${type.split('/')[1]}`)),
    '🎤 आवाज़ भेजी जा रही है…',
  );
}

micBtn.addEventListener('click', () => {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  } else {
    startRecording();
  }
});

// --- S16: location --------------------------------------------------------------------------

locationBtn.addEventListener('click', () => {
  if (!navigator.geolocation) {
    appendMessage('error', 'यह ब्राउज़र लोकेशन साझा नहीं कर सकता। कृपया अपना वार्ड लिखें।');
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (position) => {
      const { latitude, longitude } = position.coords;
      handleTurn(
        () =>
          postToApi((form) => {
            form.append('lat', String(latitude));
            form.append('lng', String(longitude));
          }),
        '📍 लोकेशन साझा की गई',
      );
    },
    () => {
      appendMessage('error', 'लोकेशन नहीं मिल सकी। कृपया अपना वार्ड या इलाका लिखें।');
    },
    { enableHighAccuracy: true, timeout: 10000 },
  );
});

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
