// Samadhan floating chat widget -- T53/T54 (S19 REVISION 2). Real backend, full parity with
// app.js: text, tap-to-record voice with live waveform, GPS location, TTS speak buttons, restart/cancel, and the
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
  const MIN_HOLD_MS = 400; // S18 D-S18-1 (shortest recording that is sent)
  const MAX_RECORD_MS = 60000; // tap-to-record stops by itself after one minute
  const WAVE_BARS = 40;
  const MIC_IDLE_CAPTION = '🎤 बोलने के लिए माइक दबाएँ · Tap to speak';

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
  // S31: shows the logged-in phone (masked); tap to log out. Hidden until the citizen has logged in.
  const authChip = document.createElement('button');
  authChip.type = 'button';
  authChip.id = 'samadhan-widget-auth';
  authChip.hidden = true;
  header.appendChild(title);
  header.appendChild(authChip);
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
  // Status check: opens the existing status page in a new tab, so the chat stays open (same session).
  const statusLink = document.createElement('a');
  statusLink.className = 'chip-btn chip-link';
  statusLink.href = 'status.html';
  statusLink.target = '_blank';
  statusLink.rel = 'noopener';
  statusLink.textContent = 'स्थिति जानें';
  actionsRow.appendChild(statusLink);

  const voiceRow = document.createElement('div');
  voiceRow.className = 'voice-row';
  const micBtn = document.createElement('button');
  micBtn.type = 'button';
  micBtn.className = 'mic-btn';
  micBtn.setAttribute('aria-label', 'आवाज़ रिकॉर्ड करने के लिए दबाएँ');
  micBtn.appendChild(svgIcon(MIC_PATH.concat(MIC_STEM), 26));
  const micTimerEl = document.createElement('span');
  micTimerEl.className = 'mic-timer';
  micTimerEl.hidden = true;
  micTimerEl.textContent = '0:00';
  const waveCanvas = document.createElement('canvas');
  waveCanvas.className = 'mic-wave';
  waveCanvas.hidden = true;
  waveCanvas.setAttribute('aria-hidden', 'true');
  const liveRow = document.createElement('div'); // timer + wave, shown only while recording
  liveRow.className = 'mic-live';
  liveRow.hidden = true;
  liveRow.appendChild(micTimerEl);
  liveRow.appendChild(waveCanvas);
  const micCaption = document.createElement('p');
  micCaption.className = 'mic-caption';
  micCaption.textContent = MIC_IDLE_CAPTION;
  voiceRow.appendChild(liveRow);
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

  // Last resort when the server voice (Sarvam / Gemini) is down, out of credit or rate limited: the browser's own Hindi voice. It exposes the few
  // parts of the Audio API the voice note and the speaker button use, so they work unchanged. No duration or progress bar (the browser does not report them).
  function browserHindiVoice() {
    if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') return null;
    return window.speechSynthesis.getVoices().find((v) => /^hi\b/i.test(v.lang)) || null;
  }

  class BrowserVoice {
    constructor(text, voice) {
      this.text = text;
      this.voice = voice;
      this.paused = true;
      this.duration = NaN;
      this.currentTime = 0;
      this.readyState = 0;
      this.preload = '';
      this.listeners = {};
      this.started = false;
    }
    addEventListener(name, fn) { (this.listeners[name] = this.listeners[name] || []).push(fn); }
    emit(name) { (this.listeners[name] || []).forEach((fn) => fn()); }
    load() {}
    play() {
      const synth = window.speechSynthesis;
      if (this.started && synth.paused) {
        synth.resume();
      } else {
        synth.cancel();
        const utterance = new SpeechSynthesisUtterance(this.text);
        utterance.lang = 'hi-IN';
        utterance.voice = this.voice;
        utterance.onend = () => { this.paused = true; this.started = false; this.emit('ended'); };
        utterance.onerror = () => { this.paused = true; this.started = false; this.emit('pause'); };
        this.started = true;
        synth.speak(utterance);
      }
      this.paused = false;
      this.emit('play');
      return Promise.resolve();
    }
    pause() {
      window.speechSynthesis.pause();
      this.paused = true;
      this.emit('pause');
    }
  }

  // 'browser' = never call the server voice (/speak, Sarvam): read replies with the browser's Hindi voice only. For testing while there is no TTS credit.
  // Switch on with `?voice=browser` in the page address or `window.SAMADHAN_TTS_MODE = 'browser'` in config.js. Default 'server' (unchanged behaviour).
  function ttsMode() {
    let mode = window.SAMADHAN_TTS_MODE;
    try {
      mode = mode || new URLSearchParams(window.location.search).get('voice');
    } catch {
      // no address bar (tests, embedded views): keep the configured mode
    }
    return mode === 'browser' ? 'browser' : 'server';
  }

  async function fetchHindiAudio(rawText) {
    const text = spokenTextOf(rawText); // never speak the URL line (S28 4.6)
    if (!text) throw new Error(GENERIC_ERROR);
    if (ttsMode() === 'browser') {
      const voice = browserHindiVoice();
      if (!voice) throw new Error(GENERIC_ERROR); // no Hindi voice installed in this browser: the note shows "!"
      return new BrowserVoice(text, voice);
    }
    try {
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
    } catch (error) {
      const voice = browserHindiVoice();
      if (voice) return new BrowserVoice(text, voice); // server voice unavailable: read it with the browser's Hindi voice
      throw error;
    }
  }

  if ('speechSynthesis' in window) window.speechSynthesis.getVoices(); // some browsers load the voice list lazily: ask once so it is ready when needed

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
      // S31: the saved login (if any) rides along; the backend only needs it when a complaint is about to be filed.
      response = await fetch(`${API_BASE}/api/v1/message`, {
        method: 'POST',
        body: form,
        headers: window.SamadhanAuth ? window.SamadhanAuth.headers() : {},
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

  // S31: after a confirmed complaint the backend answers ask_for='login' when nobody is logged in. Show the login screen, then confirm again so
  // the same draft is filed (the backend kept it). Closing the screen keeps the draft too: typing 'हाँ' later asks to log in again.
  async function promptLogin() {
    if (!window.SamadhanAuth) return;
    const loggedIn = await window.SamadhanAuth.showLogin();
    if (loggedIn) {
      await handleTurn(() => postToApi((form) => form.append('text', 'हाँ')), 'हाँ, मेरी शिकायत दर्ज करें');
    } else {
      appendMessage('bot', 'ठीक है। जब आप तैयार हों, "हाँ" लिखें और लॉगिन करके शिकायत दर्ज करें। आपकी जानकारी सुरक्षित है।');
    }
  }

  // The citizen's own recording, shown as a playable voice note in their bubble (the speech text is never shown;
  // the backend still transcribes it for routing). Falls back to a text bubble if the browser cannot make a URL for it.
  function makeLocalVoiceNote(url, seconds) {
    const box = document.createElement('div');
    box.className = 'voice-note voice-note-mine';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'vn-play';
    btn.setAttribute('aria-label', 'अपनी रिकॉर्डिंग सुनें');
    btn.textContent = '▶';
    const track = document.createElement('div');
    track.className = 'vn-track';
    const fill = document.createElement('div');
    fill.className = 'vn-fill';
    track.appendChild(fill);
    const time = document.createElement('span');
    time.className = 'vn-time';
    const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
    const total = Math.max(1, Math.round(seconds));
    time.textContent = fmt(total);
    box.append(btn, track, time);

    const audio = new Audio(url);
    audio.preload = 'auto';
    audio.load(); // fetch the data now (same as the bot voice note), so the first tap plays at once
    // A MediaRecorder file reports no duration, so progress is measured against the length we timed while recording.
    audio.addEventListener('timeupdate', () => {
      fill.style.width = `${Math.min(100, (audio.currentTime / total) * 100)}%`;
    });
    audio.addEventListener('play', () => { btn.textContent = '⏸'; });
    audio.addEventListener('pause', () => { btn.textContent = '▶'; });
    audio.addEventListener('ended', () => {
      btn.textContent = '▶';
      fill.style.width = '0%';
    });
    btn.addEventListener('click', () => {
      if (audio.paused) audio.play().catch(() => {});
      else audio.pause();
    });
    return box;
  }

  // Each recording is a Blob held by its object URL until revoked. Keep only the latest few playable so a long voice session
  // on a low-end phone does not pile up audio in memory; older notes stay in the chat but can no longer be replayed.
  const MAX_PLAYABLE_LOCAL_NOTES = 8;
  const localVoiceUrls = [];
  function keepLocalVoiceUrl(url, note) {
    localVoiceUrls.push({ url, note });
    while (localVoiceUrls.length > MAX_PLAYABLE_LOCAL_NOTES) {
      const old = localVoiceUrls.shift();
      URL.revokeObjectURL(old.url);
      const btn = old.note.querySelector('.vn-play');
      if (btn) btn.disabled = true;
      old.note.classList.add('vn-expired');
    }
  }
  window.addEventListener('pagehide', () => {
    localVoiceUrls.splice(0).forEach((v) => URL.revokeObjectURL(v.url));
  });

  function appendVoiceBubble(blob, seconds) {
    let url;
    try {
      url = URL.createObjectURL(blob);
    } catch {
      return null;
    }
    const el = document.createElement('div');
    el.className = 'msg citizen msg-in';
    const note = makeLocalVoiceNote(url, seconds);
    el.appendChild(note);
    keepLocalVoiceUrl(url, note);
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  async function handleTurn(apiCall, citizenBubbleText, autoSpeak = false, voice = null) {
    let needsLogin = false;
    const citizenEl = (voice && appendVoiceBubble(voice.blob, voice.seconds)) || appendMessage('citizen', citizenBubbleText);
    const showsVoiceNote = Boolean(citizenEl.firstChild?.classList?.contains('voice-note'));
    setBusy(true);
    const waitingEl = appendTypingIndicator(); // three dots while the reply is on its way
    try {
      const result = await apiCall();
      waitingEl.remove();
      if (result.transcript && !showsVoiceNote) {
        citizenEl.textContent = result.transcript; // only when the citizen's recording could not be shown as a voice note
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
      needsLogin = result.ask_for === 'login';
    } catch (err) {
      appendMessage('error', err.message || GENERIC_ERROR);
    } finally {
      waitingEl.remove();
      setBusy(false);
      input.focus();
    }
    if (needsLogin) await promptLogin();
  }

  if (window.SamadhanAuth) {
    window.SamadhanAuth.onChange((auth) => {
      authChip.hidden = !auth;
      authChip.textContent = auth ? `📱 ${auth.phone_masked} ✕` : '';
      authChip.setAttribute('aria-label', auth ? `लॉगआउट करें, ${auth.phone_masked}` : 'लॉगआउट');
    });
    authChip.addEventListener('click', async () => {
      await window.SamadhanAuth.logout();
      appendMessage('bot', 'आप लॉगआउट हो गए हैं।');
    });
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

  // --- Tap-to-record: tap the mic to start, tap again to send; stops by itself after 1 minute ---

  let mediaRecorder = null;
  let recordedChunks = [];
  let recordingStartedAt = 0;
  let stopRequested = false; // a tap that arrives while the mic is still connecting cancels it
  let recordingTimerInterval = null;
  let autoStopTimeout = null;
  let audioCtx = null;
  let analyser = null;
  let waveFrame = 0;
  let waveLevels = [];

  function clearMicTimer() {
    if (recordingTimerInterval) {
      clearInterval(recordingTimerInterval);
      recordingTimerInterval = null;
    }
    if (autoStopTimeout) {
      clearTimeout(autoStopTimeout);
      autoStopTimeout = null;
    }
    micTimerEl.hidden = true;
    micTimerEl.textContent = '0:00';
    liveRow.hidden = true;
  }

  // Live "pitch wave": newest loudness bar enters on the right and scrolls left, like a WhatsApp voice note.
  function drawWave() {
    const dpr = window.devicePixelRatio || 1;
    const width = waveCanvas.clientWidth;
    const height = waveCanvas.clientHeight;
    if (!width || !height) return;
    if (waveCanvas.width !== Math.round(width * dpr)) {
      waveCanvas.width = Math.round(width * dpr);
      waveCanvas.height = Math.round(height * dpr);
    }
    const ctx = waveCanvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = getComputedStyle(waveCanvas).color;
    const slot = width / WAVE_BARS;
    const barWidth = Math.max(2, slot * 0.6);
    for (let i = 0; i < WAVE_BARS; i += 1) {
      const level = waveLevels[waveLevels.length - WAVE_BARS + i] || 0;
      const barHeight = Math.max(4, level * height);
      const x = i * slot + (slot - barWidth) / 2;
      const y = (height - barHeight) / 2;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, y, barWidth, barHeight, barWidth / 2);
      else ctx.rect(x, y, barWidth, barHeight);
      ctx.fill();
    }
  }

  function startWave(stream) {
    waveLevels = [];
    waveCanvas.hidden = false;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {
      drawWave(); // no analyser available: flat line, recording still works
      return;
    }
    try {
      audioCtx = new AudioCtx();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      audioCtx.createMediaStreamSource(stream).connect(analyser);
    } catch {
      audioCtx = null;
      analyser = null;
      drawWave();
      return;
    }
    const samples = new Uint8Array(analyser.fftSize);
    // A fixed timer, not requestAnimationFrame: the bar rate must not depend on the screen's frame rate.
    waveFrame = setInterval(() => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const sample of samples) {
        const v = (sample - 128) / 128;
        sum += v * v;
      }
      // speech is quiet (RMS ~0.02-0.2): boost and curve it so ordinary talking fills most of the height
      waveLevels.push(Math.pow(Math.min(1, Math.sqrt(sum / samples.length) * 7), 0.6));
      if (waveLevels.length > WAVE_BARS) waveLevels.shift();
      drawWave();
    }, 55);
  }

  function stopWave() {
    if (waveFrame) clearInterval(waveFrame);
    waveFrame = 0;
    if (audioCtx) audioCtx.close().catch(() => {});
    audioCtx = null;
    analyser = null;
    waveLevels = [];
    waveCanvas.hidden = true;
  }

  function setMicIdle() {
    micBtn.classList.remove('mic-btn-starting', 'mic-btn-recording', 'mic-btn-cancelled');
    micBtn.setAttribute('aria-label', 'आवाज़ रिकॉर्ड करने के लिए दबाएँ');
    micCaption.textContent = MIC_IDLE_CAPTION;
    clearMicTimer();
    stopWave();
  }

  function setMicStarting() {
    micBtn.classList.add('mic-btn-starting');
    micBtn.setAttribute('aria-label', 'माइक जुड़ रहा है…');
    micCaption.textContent = 'माइक जुड़ रहा है… · Connecting…';
  }

  function setMicRecording() {
    micBtn.classList.remove('mic-btn-starting');
    micBtn.classList.add('mic-btn-recording');
    micBtn.setAttribute('aria-label', 'रिकॉर्ड हो रहा है… भेजने के लिए दोबारा दबाएँ');
    micCaption.textContent = 'सुन रहे हैं… भेजने के लिए दोबारा दबाएँ · Tap to send';
    micTimerEl.hidden = false;
    liveRow.hidden = false;
    const startedAt = Date.now();
    recordingTimerInterval = setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - startedAt) / 1000);
      micTimerEl.textContent = `${Math.floor(elapsedSec / 60)}:${String(elapsedSec % 60).padStart(2, '0')}`;
    }, 250);
    autoStopTimeout = setTimeout(stopRecording, MAX_RECORD_MS);
  }

  function flashMicCancelled() {
    clearMicTimer();
    micBtn.classList.remove('mic-btn-recording', 'mic-btn-starting');
    micBtn.classList.add('mic-btn-cancelled');
    micBtn.setAttribute('aria-label', 'रद्द');
    micCaption.textContent = 'बहुत छोटी रिकॉर्डिंग, रद्द · Too short';
    setTimeout(setMicIdle, 900);
  }

  async function beginRecording() {
    stopRequested = false;
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

    if (stopRequested) {
      stream.getTracks().forEach((track) => track.stop());
      setMicIdle();
      return;
    }

    recordedChunks = [];
    try {
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) recordedChunks.push(event.data);
      };
      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        stopWave();
        const recordedMs = performance.now() - recordingStartedAt;
        if (recordedMs < MIN_HOLD_MS) {
          flashMicCancelled();
          return;
        }
        setMicIdle();
        void sendRecording(mediaRecorder.mimeType, recordedMs / 1000);
      };
      mediaRecorder.start();
    } catch {
      // A recorder that cannot start (unsupported browser/format) must not leave the mic stuck on "connecting".
      stream.getTracks().forEach((track) => track.stop());
      mediaRecorder = null;
      appendMessage('error', 'आवाज़ रिकॉर्ड नहीं हो सकी। कृपया लिखकर भेजें।');
      setMicIdle();
      return;
    }
    recordingStartedAt = performance.now();
    setMicRecording();
    startWave(stream);
  }

  function stopRecording() {
    stopRequested = true;
    if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
  }

  function isMicRecording() {
    return Boolean(mediaRecorder && mediaRecorder.state === 'recording');
  }

  async function sendRecording(mimeType, seconds) {
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
      { blob, seconds },
    );
  }

  micBtn.addEventListener('click', () => {
    if (isMicRecording()) stopRecording();
    else if (micBtn.classList.contains('mic-btn-starting')) stopRequested = true; // tap while connecting = cancel
    else void beginRecording();
  });
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
      await new Audio('greeting-hi.mp3').play();
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
