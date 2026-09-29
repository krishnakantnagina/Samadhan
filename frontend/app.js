// Samadhan citizen chat — T21. Talks only to POST /api/v1/message (S01 contract).
// No business logic here: every action/reply comes from the backend as-is.

// Real backend (T18 shipped the real /message route; matches status.js's API_BASE, S15 G-S15-1).
const API_BASE = window.SAMADHAN_API_BASE || 'http://localhost:8000'; // config.js, S22

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

// S28 4.6: a URL in a bot reply becomes a real link, but ONLY an https `*.gov.in` homepage (the backend has
// already validated it; this is the second, independent check). Anything else stays plain text. Built with
// the DOM, never innerHTML. The line holding a URL is never sent to text-to-speech.
const URL_RE = /(https?:\/\/[^\s]+)/g;

function isGovLink(candidate) {
  try {
    const url = new URL(candidate);
    return url.protocol === 'https:' && url.hostname.endsWith('.gov.in') && !url.username && !url.port;
  } catch {
    return false;
  }
}

function fillBotText(el, text) {
  el.textContent = '';
  const parts = text.split(URL_RE);
  for (const part of parts) {
    if (!part) continue;
    if (part.startsWith('http') && isGovLink(part)) {
      const a = document.createElement('a');
      a.href = part;
      a.textContent = part;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      el.appendChild(a);
    } else {
      el.appendChild(document.createTextNode(part));
    }
  }
}

function spokenTextOf(text) {
  return text
    .split('\n')
    .filter((line) => !/https?:\/\//.test(line))
    .join(' ')
    .trim();
}

function appendMessage(role, text) {
  const el = document.createElement('div');
  el.className = `msg ${role} msg-in`; // T52: gentle arrival animation, reveal-up keyframe (S18)
  if (role === 'bot') fillBotText(el, text);
  else el.textContent = text;
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

async function fetchHindiAudio(rawText) {
  const text = spokenTextOf(rawText); // never speak the URL line (S28 4.6)
  if (!text) throw new Error(GENERIC_ERROR);
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

// S17 D-S17-5: every bot reply carries a WhatsApp-style voice note (play/pause, progress, time).
// Audio is fetched as soon as the reply appears; it auto-plays only when `autoPlay` is set (a
// reply to the citizen's own voice message, D-S17-4). If TTS fails the note shows '!' and a tap
// retries -- never a chat bubble, never a raw error (T50).
function makeVoiceNote(text, autoPlay) {
  const box = document.createElement('div');
  box.className = 'voice-note';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'vn-play';
  btn.setAttribute('aria-label', 'सुनें');
  const track = document.createElement('div');
  track.className = 'vn-track';
  const fill = document.createElement('div');
  fill.className = 'vn-fill';
  track.appendChild(fill);
  const time = document.createElement('span');
  time.className = 'vn-time';
  time.textContent = '0:00';
  box.append(btn, track, time);

  const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  let audio = null;

  async function load() {
    if (audio) return audio;
    btn.textContent = '…';
    btn.disabled = true;
    try {
      const a = await fetchHindiAudio(text);
      ['loadedmetadata', 'durationchange'].forEach((evt) => a.addEventListener(evt, () => {
        if (Number.isFinite(a.duration)) time.textContent = fmt(a.duration);
      }));
      a.addEventListener('timeupdate', () => {
        if (a.duration) fill.style.width = `${(a.currentTime / a.duration) * 100}%`;
      });
      a.addEventListener('play', () => { btn.textContent = '⏸'; });
      a.addEventListener('pause', () => { btn.textContent = '▶'; });
      a.addEventListener('ended', () => {
        btn.textContent = '▶';
        fill.style.width = '0%';
      });
      if (a.readyState >= 1 && Number.isFinite(a.duration)) time.textContent = fmt(a.duration); // metadata may already have loaded
      a.preload = 'auto';
      a.load(); // fetch the data now so the duration shows before the first play
      audio = a;
      btn.textContent = '▶';
      return a;
    } catch {
      btn.textContent = '!'; // tap to retry
      throw new Error('tts');
    } finally {
      btn.disabled = false;
    }
  }

  btn.addEventListener('click', async () => {
    try {
      const a = await load();
      if (a.paused) await a.play();
      else a.pause();
    } catch {
      // load() already showed '!'; play() rejections (autoplay policy) leave the ▶ button ready
    }
  });

  load()
    .then((a) => (autoPlay ? a.play() : undefined))
    .catch(() => {}); // autoplay blocked or TTS down: the button is the fallback
  return box;
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
  // S29: a link straight to this complaint's status page
  const statusLink = document.createElement('a');
  statusLink.className = 'ticket-status-link';
  statusLink.href = `status.html?id=${encodeURIComponent(ticket.complaint_id)}`;
  statusLink.textContent = 'स्थिति देखें';
  card.appendChild(statusLink);
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

function replaceSpeakWithVoiceNote(botEl, text, autoPlay) {
  const old = botEl.querySelector('.speak-btn');
  if (old) old.remove();
  botEl.appendChild(makeVoiceNote(text, autoPlay));
}

// --- S23: "are you at the place of the problem?" -------------------------------------------------
// Chips under a location question; typed or spoken yes/no is answered the same way. GPS/routing on
// the backend is untouched: yes -> the existing lat/lng turn, no -> an ordinary place-name turn.

let awaitingLocationChoice = false;
const LOCATION_YES = new Set([
  'हाँ', 'हां', 'हा', 'जी', 'जी हाँ', 'जी हां', 'yes', 'y', 'ok', 'okay', 'ठीक है',
  'हाँ मैं यहीं हूँ', 'हां मैं यहीं हूं', 'यहीं हूँ', 'यहीं हूं',
]);
const LOCATION_NO = new Set([
  'नहीं', 'नही', 'ना', 'जी नहीं', 'no', 'n', 'नहीं मैं यहाँ नहीं हूँ', 'मैं यहाँ नहीं हूँ',
  'घर पर हूँ', 'मैं घर पर हूँ',
]);
const LOCATION_NO_REPLY =
  'ठीक है। कृपया अपने गाँव, मोहल्ले या वार्ड का नाम बताइए (बोलकर या लिखकर)।';

function locationChoiceOf(text) {
  const cleaned = (text || '')
    .toLowerCase()
    .replace(/[.,।!?]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .join(' ');
  if (LOCATION_YES.has(cleaned)) return 'yes';
  if (LOCATION_NO.has(cleaned)) return 'no';
  return null;
}

function removeLocationChoiceChips() {
  document.querySelectorAll('.location-choice').forEach((el) => el.remove());
}

function chooseLocation(choice) {
  awaitingLocationChoice = false;
  removeLocationChoiceChips();
  setLocationHighlight(false);
  if (choice === 'yes') {
    shareLocation();
    return;
  }
  const botEl = appendMessage('bot', LOCATION_NO_REPLY);
  replaceSpeakWithVoiceNote(botEl, LOCATION_NO_REPLY, true); // the chip tap was a gesture
  inputEl.focus();
}

function appendLocationChoiceChips(botEl) {
  removeLocationChoiceChips(); // only the latest location question keeps them
  const row = document.createElement('div');
  row.className = 'location-choice';
  const yes = document.createElement('button');
  yes.type = 'button';
  yes.className = 'chip-btn chip-btn-highlight';
  yes.textContent = '📍 हाँ, मैं यहीं हूँ';
  yes.addEventListener('click', () => chooseLocation('yes'));
  const no = document.createElement('button');
  no.type = 'button';
  no.className = 'chip-btn';
  no.textContent = '✍️ नहीं, मैं नाम बताऊँगा';
  no.addEventListener('click', () => chooseLocation('no'));
  row.append(yes, no);
  botEl.appendChild(row);
}

async function handleTurn(apiCall, citizenBubbleText, autoSpeak = false) {
  const citizenEl = appendMessage('citizen', citizenBubbleText);
  setBusy(true);

  try {
    const result = await apiCall();
    if (result.transcript) {
      citizenEl.textContent = result.transcript; // S16 D-S16-3: show what was actually heard
    }
    setLocationHighlight(result.ask_for === 'location'); // S16 D-S16-1 / S01 D-A4
    const spokenChoice = awaitingLocationChoice ? locationChoiceOf(result.transcript) : null;
    if (spokenChoice && result.ask_for === 'location') {
      chooseLocation(spokenChoice); // S23: a spoken yes/no; skip the backend's re-ask bubble
      return;
    }
    awaitingLocationChoice = result.ask_for === 'location';
    const botEl = appendMessage('bot', result.reply_text);
    replaceSpeakWithVoiceNote(botEl, result.reply_text, autoSpeak);
    if (awaitingLocationChoice) appendLocationChoiceChips(botEl);
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
  const typedChoice = awaitingLocationChoice ? locationChoiceOf(trimmed) : null;
  if (typedChoice) {
    appendMessage('citizen', trimmed); // S23: answered locally, not sent
    chooseLocation(typedChoice);
    return;
  }
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
    true, // S17 D-S17-4: auto-speak the reply to a voice message
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

function shareLocation() {
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
}

locationBtn.addEventListener('click', shareLocation);

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

// A visitor who doesn't know the chat is below the hero: if they haven't scrolled or touched
// anything after 3 seconds, scroll down to it for them. Any interaction cancels this.
if (appShell) {
  const cancelAutoScroll = () => clearTimeout(autoScrollTimer);
  const autoScrollTimer = setTimeout(() => {
    ['wheel', 'touchstart', 'keydown', 'pointerdown', 'scroll'].forEach((evt) =>
      window.removeEventListener(evt, cancelAutoScroll),
    );
    if (window.scrollY > 10) return; // already scrolled, nothing to do
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    appShell.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' });
  }, 3000);
  ['wheel', 'touchstart', 'keydown', 'pointerdown', 'scroll'].forEach((evt) =>
    window.addEventListener(evt, cancelAutoScroll, { passive: true, once: true }),
  );
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

// --- S30: greeting voice on the first touch, Hindi then English --------------------------------
// Browsers refuse sound that starts before the visitor touches the page, so the FIRST touch (a tap, click or key) is what
// plays the greeting. It also unlocks one shared audio element (needed on iPhone Safari) and asks for the microphone once.
// Everything is best-effort inside try/catch: a failure means "do nothing", never an error for the citizen (T50).
const SPOKEN_EN =
  "Hello! I'm Samadhan. Tell me your problem or complaint, ask about a government service, or check the status " +
  "of your complaint. You can speak your message or type it. We'll do our best to help you.";
const SILENT_WAV = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';

const greetingAudio = new Audio(); // ONE shared element, unlocked by the first touch
let greetingState = 'idle'; // idle -> playing -> done
let greetingTextVisible = false;
let touchedBeforeGreeting = false;
let greetingSpokenHi = '';
let greetingListenBtn = null;
let firstTouchDone = false;

async function fetchSpeechSrc(rawText, language) {
  const text = spokenTextOf(rawText);
  if (!text) throw new Error(GENERIC_ERROR);
  let response;
  try {
    response = await fetch(`${API_BASE}/api/v1/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, language }),
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
  if (!response.ok) throw new Error(body.reply_text || GENERIC_ERROR);
  return `data:audio/wav;base64,${body.audio_base64}`;
}

function playOnGreetingElement(src) {
  return new Promise((resolve, reject) => {
    greetingAudio.onended = () => resolve();
    greetingAudio.onerror = () => reject(new Error('audio'));
    greetingAudio.src = src;
    const started = greetingAudio.play();
    if (started) started.catch(reject);
  });
}

async function playGreetingVoice() {
  if (greetingState !== 'idle') return; // never two playbacks at once
  greetingState = 'playing';
  if (greetingListenBtn) greetingListenBtn.hidden = true;
  try {
    const hiSrc = await fetchSpeechSrc(greetingSpokenHi, 'hi');
    const enPromise = fetchSpeechSrc(SPOKEN_EN, 'en').catch(() => null); // fetched while Hindi plays
    await playOnGreetingElement(hiSrc);
    const enSrc = await enPromise;
    if (enSrc) {
      try {
        await playOnGreetingElement(enSrc);
      } catch {
        // English failed after Hindi was heard: nothing more to do
      }
    }
    greetingState = 'done';
  } catch {
    greetingState = 'idle'; // blocked or failed: the visible button lets the citizen try again
    if (greetingListenBtn) greetingListenBtn.hidden = false;
  }
}

function unlockGreetingAudio() {
  if (greetingState !== 'idle') return; // never cut a greeting that is already playing
  try {
    greetingAudio.src = SILENT_WAV;
    const started = greetingAudio.play();
    if (started) started.catch(() => {});
  } catch {
    // not unlockable in this browser: the greeting button still works
  }
}

async function primeMicPermission(target) {
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    if (!navigator.permissions || !navigator.permissions.query) return; // e.g. Safari: ask at the first hold instead
    if (target && micBtn && (target === micBtn || micBtn.contains(target))) return; // the mic press asks for itself
    const status = await navigator.permissions.query({ name: 'microphone' });
    if (status.state !== 'prompt') return; // already granted or denied: never ask twice
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop()); // release at once: no recording, no indicator left on
  } catch {
    // denied or unavailable: the mic button shows its own Hindi message when used, typing always works
  }
}

function onFirstTouch(event) {
  if (firstTouchDone) return;
  firstTouchDone = true;
  unlockGreetingAudio();
  if (greetingTextVisible) playGreetingVoice();
  else touchedBeforeGreeting = true; // the greeting starts speaking as soon as its text appears
  primeMicPermission(event.target);
}

// Only these events count as a user gesture for sound (a bare pointerdown or scroll does not).
['pointerup', 'touchend', 'mousedown', 'keydown', 'click'].forEach((name) => {
  document.addEventListener(name, onFirstTouch, { capture: true, passive: true });
});

// Wake the (free, sleeping) backend now so the first voice request is not slow. Silent on failure.
try {
  fetch(`${API_BASE}/health`).catch(() => {});
} catch {
  // ignore
}

function appendGreeting() {
  const card = document.createElement('div');
  card.className = 'greeting-card';

  const hi = document.createElement('div');
  hi.className = 'greeting-block greeting-hi';
  greetingLine(hi, 'नमस्ते! मैं समाधान हूँ।', null, null);
  greetingLine(
    hi,
    'आप अपनी समस्या या शिकायत बताइए, किसी सरकारी जानकारी के बारे में पूछिए, या अपनी शिकायत की स्थिति जानिए।',
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
    'Tell me your problem or complaint, ask about a government service, or check the status of your complaint.',
    null,
    null,
  );
  greetingLine(en, 'You can ', 'speak your message or type it', ". We'll do our best to help you.");

  const listenBtn = document.createElement('button');
  listenBtn.type = 'button';
  listenBtn.className = 'greeting-listen-btn';
  listenBtn.hidden = false; // S30: visible from the start, hidden once the voice starts
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
    'नमस्ते! मैं समाधान हूँ। आप अपनी समस्या या शिकायत बताइए, किसी सरकारी जानकारी के बारे में पूछिए, ' +
    'या अपनी शिकायत की स्थिति जानिए। आप अपनी बात आवाज़ में बोलकर या लिखकर बता सकते हैं। हम आपकी सहायता ' +
    'करने की पूरी कोशिश करेंगे।';
  const wrapper = appendMessage('bot', spokenHi);
  wrapper.firstChild.textContent = ''; // clear the auto-created text node's visible content
  wrapper.insertBefore(card, wrapper.firstChild);

  // S30: the voice is started by the first touch anywhere (onFirstTouch) or by this button; see the helpers above.
  greetingSpokenHi = spokenHi;
  greetingListenBtn = listenBtn;
  greetingTextVisible = true;
  listenBtn.addEventListener('click', () => {
    unlockGreetingAudio();
    playGreetingVoice();
  });
  if (touchedBeforeGreeting || (navigator.userActivation && navigator.userActivation.hasBeenActive)) {
    playGreetingVoice();
  }

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
