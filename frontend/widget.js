// Samadhan floating chat widget -- T53/T54 (S19 REVISION 2). Real backend, full parity with
// app.js: text, press-and-hold voice, GPS location, TTS speak buttons, restart/cancel, and the
// bilingual greeting. Drop-in: add <script src="widget.js"> to any page that also loads style.css.
// Self-mounting, no HTML placeholder needed. No business logic here: every action/reply comes from
// the backend as-is, same posture as app.js. Deliberately does not import from app.js (D-S19-2):
// no build step/module system exists in this project, so this file mirrors app.js's logic against
// its own namespaced DOM (#samadhan-widget-*) rather than sharing a module.

(function () {
  const API_BASE = window.SAMADHAN_API_BASE || 'http://localhost:8000'; // config.js, S22
  const SESSION_KEY = 'samadhan_session_id'; // D-S19-1: same key app.js uses -- same conversation
  const SEEN_KEY = 'samadhan_widget_seen';
  const GENERIC_ERROR = 'सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।';
  const ACCEPTED_AUDIO_TYPES = new Set(['audio/webm', 'audio/ogg', 'audio/mp4', 'audio/wav']);
  const MIN_HOLD_MS = 400; // S18 D-S18-1

  function getSessionId() {
    let id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  function svgIcon(pathsD, size) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', String(size || 26));
    svg.setAttribute('height', String(size || 26));
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
  const MIC_PATH = ['M9 2h6v12a3 3 0 0 1-3 3 3 3 0 0 1-3-3V2z', 'M5 10a7 7 0 0 0 14 0'];
  const MIC_STEM = ['M12 19v3'];

  // --- Build DOM ---------------------------------------------------------------------------

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
  composer.className = 'composer';

  const actionsRow = document.createElement('div');
  actionsRow.className = 'composer-actions';
  const restartBtn = document.createElement('button');
  restartBtn.type = 'button';
  restartBtn.className = 'chip-btn';
  restartBtn.textContent = 'फिर से शुरू करें';
  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'chip-btn';
  cancelBtn.textContent = 'रद्द करें';
  const locationBtn = document.createElement('button');
  locationBtn.type = 'button';
  locationBtn.className = 'chip-btn';
  locationBtn.textContent = '📍 लोकेशन भेजें';
  actionsRow.appendChild(restartBtn);
  actionsRow.appendChild(cancelBtn);
  actionsRow.appendChild(locationBtn);

  const voiceRow = document.createElement('div');
  voiceRow.className = 'voice-row';
  const micBtn = document.createElement('button');
  micBtn.type = 'button';
  micBtn.className = 'mic-btn';
  micBtn.setAttribute('aria-label', 'आवाज़ रिकॉर्ड करने के लिए दबाकर रखें');
  micBtn.appendChild(svgIcon(MIC_PATH.concat(MIC_STEM), 26));
  const micTimerEl = document.createElement('span');
  micTimerEl.className = 'mic-timer';
  micTimerEl.hidden = true;
  micTimerEl.textContent = '0:00';
  micBtn.appendChild(micTimerEl);
  const micCaption = document.createElement('p');
  micCaption.className = 'mic-caption';
  micCaption.textContent = '🎤 बोलने के लिए दबाकर रखें · Hold to speak';
  voiceRow.appendChild(micBtn);
  voiceRow.appendChild(micCaption);

  const textRow = document.createElement('div');
  textRow.className = 'composer-row';
  const input = document.createElement('textarea');
  input.className = 'input';
  input.id = 'samadhan-widget-input';
  input.rows = 1;
  input.placeholder = 'या यहाँ लिखें…';
  input.required = true;
  const sendBtn = document.createElement('button');
  sendBtn.type = 'submit';
  sendBtn.className = 'send-btn';
  sendBtn.setAttribute('aria-label', 'भेजें');
  sendBtn.textContent = 'भेजें';
  textRow.appendChild(input);
  textRow.appendChild(sendBtn);

  composer.appendChild(actionsRow);
  composer.appendChild(voiceRow);
  composer.appendChild(textRow);

  panel.appendChild(header);
  panel.appendChild(messagesEl);
  panel.appendChild(composer);
  root.appendChild(label);
  root.appendChild(panel);
  root.appendChild(toggleBtn);
  document.body.appendChild(root);

  // --- Rendering (mirrors app.js's shape; duplicated not imported, D-S19-2) -----------------

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
    el.className = `msg ${role} msg-in`;
    if (role === 'bot') fillBotText(el, text);
    else el.textContent = text;
    if (role === 'bot') {
      el.appendChild(makeSpeakButton(text));
    }
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
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
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function setBusy(busy) {
    input.disabled = busy;
    sendBtn.disabled = busy;
    restartBtn.disabled = busy;
    cancelBtn.disabled = busy;
    micBtn.disabled = busy;
    locationBtn.disabled = busy;
  }

  function normaliseAudioType(mimeType) {
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
    input.focus();
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
        citizenEl.textContent = result.transcript;
      }
      setLocationHighlight(result.ask_for === 'location');
      const spokenChoice = awaitingLocationChoice ? locationChoiceOf(result.transcript) : null;
      if (spokenChoice && result.ask_for === 'location') {
        chooseLocation(spokenChoice); // S23: a spoken yes/no; skip the backend's re-ask bubble
        return;
      }
      awaitingLocationChoice = result.ask_for === 'location';
      const botEl = appendMessage('bot', result.reply_text);
      replaceSpeakWithVoiceNote(botEl, result.reply_text, autoSpeak);
      if (awaitingLocationChoice) appendLocationChoiceChips(botEl);
      if (result.action === 'confirm' && result.summary) appendSummaryCard(botEl, result.summary);
      if (result.action === 'submitted' && result.ticket) appendTicketCard(botEl, result.ticket);
    } catch (err) {
      appendMessage('error', err.message || GENERIC_ERROR);
    } finally {
      setBusy(false);
      input.focus();
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

  composer.addEventListener('submit', (event) => {
    event.preventDefault();
    const text = input.value;
    input.value = '';
    send(text);
  });

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      composer.requestSubmit();
    }
  });

  restartBtn.addEventListener('click', () => send('restart'));
  cancelBtn.addEventListener('click', () => send('cancel'));

  // --- Press-and-hold recording (mirrors app.js's S18 logic exactly) ------------------------

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
    micTimerEl.hidden = true;
    micTimerEl.textContent = '0:00';
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
    micTimerEl.hidden = false;
    const startedAt = Date.now();
    recordingTimerInterval = setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - startedAt) / 1000);
      micTimerEl.textContent = `${Math.floor(elapsedSec / 60)}:${String(elapsedSec % 60).padStart(2, '0')}`;
    }, 250);
  }

  function flashMicCancelled() {
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
      stream.getTracks().forEach((track) => track.stop());
      setMicIdle();
      return;
    }

    recordedChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data);
    };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
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

    if (releaseRequested) mediaRecorder.stop();
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
    event.preventDefault();
    try {
      micBtn.setPointerCapture(event.pointerId); // S18 D-S18-3 (guarded, G-S18-4)
    } catch {
      // Capture is a reliability nicety; recording must still proceed if it isn't granted.
    }
    beginHold();
  });
  micBtn.addEventListener('pointerup', endHold);
  micBtn.addEventListener('pointercancel', endHold);
  micBtn.addEventListener('contextmenu', (event) => event.preventDefault());

  // --- Location ------------------------------------------------------------------------------

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

  // --- Bilingual greeting (mirrors app.js's S18 BEHAVIOR 4, Hindi audio only) ----------------

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
    listenBtn.hidden = true;
    listenBtn.textContent = '🔊 सुनने के लिए टैप करें · Tap to listen';

    card.appendChild(hi);
    card.appendChild(divider);
    card.appendChild(en);
    card.appendChild(listenBtn);

    const spokenHi =
      'नमस्ते! मैं समाधान हूँ। आप अपनी समस्या या शिकायत बताइए, किसी सरकारी जानकारी के बारे में पूछिए, ' +
      'या अपनी शिकायत की स्थिति जानिए। आप अपनी बात आवाज़ में बोलकर या लिखकर बता सकते हैं। हम आपकी सहायता ' +
      'करने की पूरी कोशिश करेंगे।';

    const wrapper = appendMessage('bot', spokenHi);
    wrapper.firstChild.textContent = '';
    wrapper.insertBefore(card, wrapper.firstChild);

    async function playGreetingAudio() {
      // S31: pre-recorded file, no TTS call (same words as spokenHi above).
      await new Audio('greeting-hi.wav').play();
    }

    listenBtn.addEventListener('click', async () => {
      listenBtn.disabled = true;
      const original = listenBtn.textContent;
      listenBtn.textContent = '…';
      try {
        await playGreetingAudio();
        listenBtn.hidden = true;
      } catch {
        listenBtn.textContent = original;
      } finally {
        listenBtn.disabled = false;
      }
    });

    playGreetingAudio().catch(() => {
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
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  // --- Open/close ------------------------------------------------------------------------------

  let opened = false;
  let greetedOnce = false;

  function setOpen(open) {
    opened = open;
    panel.hidden = !open;
    root.classList.toggle('samadhan-widget-open', open);
    if (open) root.classList.add('samadhan-widget-seen'); // S31: home page shows the round button only after the first open
    toggleBtn.textContent = '';
    toggleBtn.appendChild(svgIcon(open ? CLOSE_PATH : CHAT_PATH));
    toggleBtn.setAttribute('aria-label', open ? 'बंद करें' : 'समाधान से बात करें');
    if (open) {
      label.hidden = true;
      sessionStorage.setItem(SEEN_KEY, '1');
      if (!greetedOnce) {
        greetedOnce = true;
        const typingEl = appendTypingIndicator();
        setTimeout(() => {
          typingEl.remove();
          appendGreeting();
        }, 3000);
      }
      input.focus();
    }
  }

  // S31: the hero's "Start Conversation" mic (index.html) opens the widget. Pages without it are unaffected.
  const heroCta = document.getElementById('hero-cta');
  if (heroCta) heroCta.addEventListener('click', () => setOpen(true));
  window.SamadhanWidget = { open: () => setOpen(true) };

  toggleBtn.addEventListener('click', () => setOpen(!opened));
  closeBtn.addEventListener('click', () => setOpen(false));

  if (sessionStorage.getItem(SEEN_KEY)) {
    label.hidden = true; // D-S19-3: shown once per browser session only
  }
})();
