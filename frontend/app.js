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
  el.className = `msg ${role} msg-in`; // T52: gentle arrival animation, reveal-up keyframe (S18)
  el.textContent = text;
  if (role === 'bot') {
    // Closure over the original `text`, not read back from the DOM -- citizenEl.textContent is
    // reassigned in place for audio turns (S16 D-S16-3), but only on citizen bubbles, never bot
    // ones, so this button and el.textContent never fight over the same node (S17 plan step S8).
    el.appendChild(makeSpeakButton(text));
  }
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

function makeSpeakButton(text) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'speak-btn';
  button.textContent = '🔊';
  button.setAttribute('aria-label', 'सुनें');
  button.addEventListener('click', () => speakText(text, button));
  return button;
}

async function fetchHindiAudio(text) {
  // Real Sarvam TTS, hi-IN fixed server-side (S17 D-S17-1). Throws GENERIC_ERROR-class errors,
  // same citizen-safe posture as postToApi (T50) -- never a raw fetch/parse error escapes.
  let response;
  try {
    response = await fetch(`${API_BASE}/api/v1/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
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
  return new Audio(`data:audio/wav;base64,${body.audio_base64}`);
}

function speakEnglish(text) {
  // No backend TTS for English exists (S17's /speak is hi-IN fixed; adding a language parameter
  // is a backend change, out of T52's scope). The browser's own English voice is used instead --
  // client-side only, no new dependency.
  return new Promise((resolve, reject) => {
    if (!('speechSynthesis' in window)) {
      reject(new Error('speechSynthesis unsupported'));
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-IN';
    utterance.onend = () => resolve();
    utterance.onerror = () => reject(new Error('speechSynthesis failed'));
    window.speechSynthesis.speak(utterance);
  });
}

async function speakText(text, button) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = '…';
  try {
    const audio = await fetchHindiAudio(text);
    await audio.play();
    button.textContent = original;
  } catch {
    // Brief inline failure state on the button itself -- a failed "listen" tap is not a failed
    // turn, so this never adds a new chat bubble (S17 BEHAVIOR 2 step 4).
    button.textContent = '!';
    setTimeout(() => {
      button.textContent = original;
    }, 1500);
  } finally {
    button.disabled = false;
  }
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
  card.className = 'card card-ticket card-ticket-confirm'; // T52: confirmation pop (S18)
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

// --- S18: press-and-hold recording (replaces S16's tap-to-toggle trigger) -------------------

const MIN_HOLD_MS = 400; // D-S18-1
const micTimerEl = document.getElementById('mic-timer');

let mediaRecorder = null;
let recordedChunks = [];
let holdStartedAt = 0;
let releaseRequested = false;
let recordingTimerInterval = null;

function clearMicTimer() {
  if (recordingTimerInterval) {
    clearInterval(recordingTimerInterval);
    recordingTimerInterval = null;
  }
  if (micTimerEl) {
    micTimerEl.hidden = true;
    micTimerEl.textContent = '0:00';
  }
}

function setMicIdle() {
  micBtn.classList.remove('mic-btn-starting', 'mic-btn-recording', 'mic-btn-cancelled');
  micBtn.setAttribute('aria-label', 'आवाज़ रिकॉर्ड करने के लिए दबाकर रखें');
  clearMicTimer();
}

function setMicStarting() {
  micBtn.classList.add('mic-btn-starting');
  micBtn.setAttribute('aria-label', 'शुरू हो रहा है…');
}

function setMicRecording() {
  micBtn.classList.remove('mic-btn-starting');
  micBtn.classList.add('mic-btn-recording');
  micBtn.setAttribute('aria-label', 'रिकॉर्ड हो रहा है… छोड़ने पर भेजा जाएगा');
  if (micTimerEl) {
    micTimerEl.hidden = false;
    const startedAt = Date.now();
    recordingTimerInterval = setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - startedAt) / 1000);
      micTimerEl.textContent = `${Math.floor(elapsedSec / 60)}:${String(elapsedSec % 60).padStart(2, '0')}`;
    }, 250);
  }
}

function flashMicCancelled() {
  // Same brief-inline-flash idiom S17's speak button uses (D-S18-5) -- no new chat bubble, a
  // cancelled tap is not a failed turn.
  clearMicTimer();
  micBtn.classList.remove('mic-btn-recording', 'mic-btn-starting');
  micBtn.classList.add('mic-btn-cancelled');
  micBtn.setAttribute('aria-label', 'रद्द');
  setTimeout(setMicIdle, 900);
}

async function beginHold() {
  holdStartedAt = performance.now();
  releaseRequested = false;
  setMicStarting();

  if (!navigator.mediaDevices?.getUserMedia) {
    appendMessage('error', 'यह ब्राउज़र आवाज़ रिकॉर्ड नहीं कर सकता। कृपया लिखकर भेजें।');
    setMicIdle();
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    appendMessage('error', 'माइक्रोफ़ोन का उपयोग नहीं हो सका। कृपया अनुमति दें या लिखकर भेजें।');
    setMicIdle();
    return;
  }

  if (releaseRequested) {
    // S18 BEHAVIOR 1 step 3: released before permission resolved -- never start a recording
    // nobody is still holding for.
    stream.getTracks().forEach((track) => track.stop());
    setMicIdle();
    return;
  }

  recordedChunks = [];
  mediaRecorder = new MediaRecorder(stream); // S16 D-S16-2: no explicit mimeType, browser default
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) recordedChunks.push(event.data);
  };
  mediaRecorder.onstop = () => {
    stream.getTracks().forEach((track) => track.stop()); // S16 RULES 5, unchanged
    const held = performance.now() - holdStartedAt;
    if (held < MIN_HOLD_MS) {
      flashMicCancelled();
      return;
    }
    setMicIdle();
    void sendRecording(mediaRecorder.mimeType);
  };
  mediaRecorder.start();
  setMicRecording();

  if (releaseRequested) mediaRecorder.stop(); // finger lifted while getUserMedia was resolving
}

function endHold() {
  releaseRequested = true;
  if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
}

async function sendRecording(mimeType) {
  const type = normaliseAudioType(mimeType);
  if (!ACCEPTED_AUDIO_TYPES.has(type)) {
    appendMessage('error', 'यह ऑडियो प्रारूप समर्थित नहीं है। कृपया लिखकर भेजें।');
    return;
  }
  const blob = new Blob(recordedChunks, { type });
  await handleTurn(
    () => postToApi((form) => form.append('audio', blob, `recording.${type.split('/')[1]}`)),
    '🎤 आवाज़ भेजी जा रही है…',
  );
}

micBtn.addEventListener('pointerdown', (event) => {
  event.preventDefault(); // avoid a delayed synthetic click firing after touch release
  try {
    micBtn.setPointerCapture(event.pointerId); // S18 D-S18-3
  } catch {
    // Capture is a reliability nicety (keeps release tracked if the finger drifts off the
    // button); if the browser can't grant it, recording must still proceed uninterrupted.
  }
  beginHold();
});
micBtn.addEventListener('pointerup', endHold);
micBtn.addEventListener('pointercancel', endHold);
micBtn.addEventListener('contextmenu', (event) => event.preventDefault()); // no long-press menu

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

// --- T52: bilingual greeting (S18 BEHAVIOR 2) -------------------------------------------------

function greetingLine(container, before, bold, after) {
  const p = document.createElement('p');
  p.className = 'greeting-line';
  if (before) p.appendChild(document.createTextNode(before));
  if (bold) {
    const strong = document.createElement('strong');
    strong.textContent = bold;
    p.appendChild(strong);
  }
  if (after) p.appendChild(document.createTextNode(after));
  container.appendChild(p);
}

function appendGreeting() {
  const card = document.createElement('div');
  card.className = 'greeting-card';

  const hi = document.createElement('div');
  hi.className = 'greeting-block greeting-hi';
  greetingLine(hi, 'नमस्ते! मैं समाधान हूँ।', null, null);
  greetingLine(
    hi,
    'आप अपनी समस्या हमें बताइए, या किसी भी सरकारी सेवा से जुड़ी जानकारी चाहिए तो बेझिझक पूछिए।',
    null,
    null,
  );
  greetingLine(
    hi,
    'आप अपनी बात ',
    'आवाज़ में बोलकर या लिखकर',
    ' बता सकते हैं। हम आपकी सहायता करने की पूरी कोशिश करेंगे।',
  );

  const divider = document.createElement('div');
  divider.className = 'greeting-divider';

  const en = document.createElement('div');
  en.className = 'greeting-block greeting-en';
  greetingLine(en, "Hello! I'm Samadhan.", null, null);
  greetingLine(
    en,
    'Please tell me about your problem, or ask me if you need information about any government service.',
    null,
    null,
  );
  greetingLine(en, 'You can ', 'speak your message or type it', ". We'll do our best to help you.");

  const listenBtn = document.createElement('button');
  listenBtn.type = 'button';
  listenBtn.className = 'greeting-listen-btn';
  listenBtn.hidden = true; // shown only if autoplay below is blocked by the browser
  listenBtn.textContent = '🔊 सुनने के लिए टैप करें · Tap to listen';

  card.appendChild(hi);
  card.appendChild(divider);
  card.appendChild(en);
  card.appendChild(listenBtn);

  // Reuse the existing bot-bubble shell and its speak button (S17). The speak button's closure
  // needs real text to synthesize -- TTS is hi-IN fixed (S17 D-S17-1), so only the Hindi portion
  // is passed, not the English. appendMessage's own textContent write becomes an empty text node
  // once cleared below, so the card is the only thing actually visible.
  const spokenHi =
    'नमस्ते! मैं समाधान हूँ। आप अपनी समस्या हमें बताइए, या किसी भी सरकारी सेवा से जुड़ी जानकारी ' +
    'चाहिए तो बेझिझक पूछिए। आप अपनी बात आवाज़ में बोलकर या लिखकर बता सकते हैं। हम आपकी सहायता ' +
    'करने की पूरी कोशिश करेंगे।';
  const spokenEn =
    "Hello! I'm Samadhan. Please tell me about your problem, or ask me if you need information " +
    "about any government service. You can speak your message or type it. We'll do our best to " +
    'help you.';

  const wrapper = appendMessage('bot', spokenHi);
  wrapper.firstChild.textContent = ''; // clear the auto-created text node's visible content
  wrapper.insertBefore(card, wrapper.firstChild);

  async function playBothLanguages() {
    const audio = await fetchHindiAudio(spokenHi); // throws if this fails -- caller catches
    await audio.play(); // browsers reject this without a prior user gesture (autoplay policy)
    await speakEnglish(spokenEn).catch(() => {}); // English is a bonus; Hindi already got through
  }

  listenBtn.addEventListener('click', async () => {
    listenBtn.disabled = true;
    const original = listenBtn.textContent;
    listenBtn.textContent = '…';
    try {
      await playBothLanguages();
      listenBtn.hidden = true; // a real click is always an allowed gesture -- this always works
    } catch {
      listenBtn.textContent = original;
    } finally {
      listenBtn.disabled = false;
    }
  });

  // Best-effort autoplay. Most browsers block unprompted audio before the citizen has interacted
  // with the page at all (Chrome/Safari/Firefox's autoplay policy -- not something client code can
  // override) -- so this frequently fails on a genuinely first visit, by design, not a bug. Never
  // a silent dead end: the listen button above appears the moment it does.
  playBothLanguages().catch(() => {
    listenBtn.hidden = false;
  });

  return wrapper;
}

function appendTypingIndicator() {
  const el = document.createElement('div');
  el.className = 'msg bot msg-in';
  const dots = document.createElement('span');
  dots.className = 'typing-indicator';
  for (let i = 0; i < 3; i += 1) dots.appendChild(document.createElement('span'));
  el.appendChild(dots);
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

// Brief pause before the greeting appears, like a chatbot "typing," then the bilingual greeting
// renders and both languages attempt to auto-play (user-requested behavior).
const typingEl = appendTypingIndicator();
setTimeout(() => {
  typingEl.remove();
  appendGreeting();
}, 3000);
