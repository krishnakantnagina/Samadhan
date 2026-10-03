// Code-level tests for the widget's tap-to-record mic (frontend/widget.js): tap to start, live waveform, tap to send, 60 s auto-stop.
// Run: `node --test frontend/tests`. The widget is loaded into a vm sandbox with a tiny fake DOM, fake timers, a fake MediaRecorder and a
// fake microphone, so no browser is needed. Real-device behaviour (permission prompt, how the wave looks) is still checked by hand.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../widget.js', import.meta.url), 'utf8');

class FakeEl {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.attrs = {};
    this.listeners = {};
    this.classes = new Set();
    this.hidden = false;
    this.disabled = false;
    this.value = '';
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this.clientWidth = 240;
    this.clientHeight = 40;
    this.width = 0;
    this.height = 0;
    this._text = '';
    this.fills = 0;
    this.classList = {
      add: (...c) => c.forEach((x) => this.classes.add(x)),
      remove: (...c) => c.forEach((x) => this.classes.delete(x)),
      toggle: (c, on) => (on ?? !this.classes.has(c) ? this.classes.add(c) : this.classes.delete(c)),
      contains: (c) => this.classes.has(c),
    };
  }
  set className(v) { this.classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get className() { return [...this.classes].join(' '); }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); }
  get firstChild() { return this.children[0] || null; }
  appendChild(c) { this.children.push(c); return c; }
  append(...cs) { cs.forEach((c) => this.children.push(c)); }
  insertBefore(c, ref) { const i = this.children.indexOf(ref); this.children.splice(i < 0 ? this.children.length : i, 0, c); return c; }
  remove() {}
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatch(type, event = {}) { (this.listeners[type] || []).forEach((fn) => fn({ preventDefault() {}, ...event })); }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  focus() {}
  getContext() {
    const el = this;
    return {
      setTransform() {}, clearRect() {}, beginPath() {}, rect() {}, roundRect() {},
      fill() { el.fills += 1; },
      set fillStyle(v) { el.fillStyle = v; },
    };
  }
}

function findAll(el, pred, out = []) {
  if (pred(el)) out.push(el);
  (el.children || []).forEach((c) => findAll(c, pred, out));
  return out;
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
}

function load({ micFails = false, recorderFails = false, blobUrls = true } = {}) {
  let now = 0;
  let nextId = 1;
  let timers = [];
  const addTimer = (fn, ms, repeat) => {
    const t = { id: nextId++, at: now + ms, fn, repeat: repeat ? ms : 0 };
    timers.push(t);
    return t.id;
  };
  const clock = {
    advance(ms) {
      const end = now + ms;
      for (;;) {
        const due = timers.filter((t) => t.at <= end).sort((a, b) => a.at - b.at)[0];
        if (!due) break;
        now = due.at;
        if (due.repeat) due.at += due.repeat;
        else timers = timers.filter((t) => t !== due);
        due.fn(now);
      }
      now = end;
    },
  };

  const body = new FakeEl('body');
  const document = {
    body,
    createElement: (tag) => new FakeEl(tag),
    createElementNS: (_ns, tag) => new FakeEl(tag),
    createTextNode: (text) => ({ textContent: text }),
    getElementById: () => null,
    querySelectorAll: () => [],
  };

  const state = { amp: 40, streams: [], recorders: [], audioContexts: [], messagePosts: [], getUserMediaCalls: 0 };

  class FakeMediaRecorder {
    constructor() {
      this.state = 'inactive';
      this.mimeType = 'audio/webm;codecs=opus';
      state.recorders.push(this);
    }
    start() {
      if (recorderFails) throw new Error('NotSupportedError');
      this.state = 'recording';
    }
    stop() {
      if (this.state !== 'recording') return;
      this.state = 'inactive';
      this.ondataavailable({ data: { size: 10 } });
      this.onstop();
    }
  }

  class FakeAudioContext {
    constructor() { this.closed = false; state.audioContexts.push(this); }
    createAnalyser() {
      return { fftSize: 0, getByteTimeDomainData: (arr) => arr.fill(128 + state.amp) };
    }
    createMediaStreamSource() { return { connect() {} }; }
    close() { this.closed = true; return Promise.resolve(); }
  }

  const store = new Map();
  const sandbox = {
    document,
    window: { SAMADHAN_API_BASE: 'http://api.test', AudioContext: FakeAudioContext, devicePixelRatio: 1 },
    navigator: {
      mediaDevices: {
        getUserMedia: async () => {
          state.getUserMediaCalls += 1;
          await flush();
          if (micFails) throw new Error('denied');
          const stream = { stopped: 0, getTracks() { return [{ stop: () => { stream.stopped += 1; } }]; } };
          state.streams.push(stream);
          return stream;
        },
      },
    },
    MediaRecorder: FakeMediaRecorder,
    sessionStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) },
    crypto: { randomUUID: () => 'uuid-1' },
    FormData: class { constructor() { this.entries = []; } append(k, v, name) { this.entries.push([k, v, name]); } },
    Blob: class { constructor(parts, opts) { this.parts = parts; this.type = opts.type; } },
    Audio: class { play() { return Promise.reject(new Error('no audio')); } addEventListener() {} load() {} },
    fetch: async (url, opts) => {
      if (String(url).endsWith('/api/v1/message')) {
        state.messagePosts.push(opts.body);
        return { ok: true, json: async () => ({ reply_text: 'ठीक है', transcript: 'नमस्ते' }) };
      }
      return { ok: false, json: async () => ({ reply_text: 'no tts in test' }) };
    },
    getComputedStyle: () => ({ color: 'rgb(122, 39, 26)' }),
    performance: { now: () => now },
    setTimeout: (fn, ms) => addTimer(fn, ms, false),
    clearTimeout: (id) => { timers = timers.filter((t) => t.id !== id); },
    setInterval: (fn, ms) => addTimer(fn, ms, true),
    clearInterval: (id) => { timers = timers.filter((t) => t.id !== id); },
    requestAnimationFrame: (fn) => addTimer(fn, 16, false),
    cancelAnimationFrame: (id) => { timers = timers.filter((t) => t.id !== id); },
    URL: blobUrls ? class extends URL { static createObjectURL() { return 'blob:test-recording'; } } : URL,
    console, Date: { now: () => now }, JSON, Math, Promise, Uint8Array, Set, Error,
  };
  sandbox.window.window = sandbox.window;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);

  const root = body.children[0];
  const byClass = (c) => findAll(root, (e) => e.classes && e.classes.has(c))[0];
  return {
    clock, state, root,
    mic: byClass('mic-btn'),
    wave: byClass('mic-wave'),
    caption: byClass('mic-caption'),
    timer: byClass('mic-timer'),
    messages: () => findAll(root, (e) => e.classes && e.classes.has('msg')),
  };
}

const tap = (mic) => mic.dispatch('click');

test('idle: tap-to-speak caption, waveform hidden', () => {
  const w = load();
  assert.match(w.caption.textContent, /Tap to speak/);
  assert.equal(w.wave.hidden, true);
  assert.equal(w.mic.classList.contains('mic-btn-recording'), false);
});

test('tap shows the connecting state until the microphone is ready', async () => {
  const w = load();
  tap(w.mic);
  assert.ok(w.mic.classList.contains('mic-btn-starting'));
  assert.match(w.caption.textContent, /Connecting/);
  assert.equal(w.state.getUserMediaCalls, 1);
  await flush();
  await flush();
  assert.ok(!w.mic.classList.contains('mic-btn-starting'));
  assert.ok(w.mic.classList.contains('mic-btn-recording'));
});

test('recording shows the live wave: bars are drawn and follow the loudness', async () => {
  const w = load();
  tap(w.mic);
  await flush(); await flush();
  assert.equal(w.wave.hidden, false);
  assert.equal(w.timer.hidden, false);
  assert.equal(w.state.recorders[0].state, 'recording');
  w.clock.advance(1000);
  assert.ok(w.wave.fills >= 40, `expected bars drawn, got ${w.wave.fills} fills`);
  assert.equal(w.timer.textContent, '0:01');
});

test('second tap stops, sends the audio, and cleans up', async () => {
  const w = load();
  tap(w.mic);
  await flush(); await flush();
  w.clock.advance(2000);
  tap(w.mic);
  await flush(); await flush();
  assert.equal(w.state.messagePosts.length, 1);
  const audio = w.state.messagePosts[0].entries.find(([k]) => k === 'audio');
  assert.ok(audio, 'audio field posted');
  assert.equal(audio[2], 'recording.webm');
  assert.equal(w.state.streams[0].stopped, 1, 'mic tracks released');
  assert.ok(w.state.audioContexts[0].closed, 'audio context closed');
  assert.equal(w.wave.hidden, true);
  assert.match(w.caption.textContent, /Tap to speak/);
  assert.equal(w.mic.classList.contains('mic-btn-recording'), false);
});

test('auto-stops and sends after one minute, not before', async () => {
  const w = load();
  tap(w.mic);
  await flush(); await flush();
  w.clock.advance(59900);
  assert.equal(w.state.recorders[0].state, 'recording');
  assert.equal(w.state.messagePosts.length, 0);
  w.clock.advance(200);
  await flush(); await flush();
  assert.equal(w.state.recorders[0].state, 'inactive');
  assert.equal(w.state.messagePosts.length, 1);
});

test('a manual stop cancels the auto-stop (nothing is sent twice)', async () => {
  const w = load();
  tap(w.mic);
  await flush(); await flush();
  w.clock.advance(3000);
  tap(w.mic);
  await flush(); await flush();
  w.clock.advance(120000);
  await flush();
  assert.equal(w.state.messagePosts.length, 1);
});

test('tap while still connecting cancels: nothing recorded or sent', async () => {
  const w = load();
  tap(w.mic);
  tap(w.mic);
  await flush(); await flush();
  assert.equal(w.state.recorders.length, 0);
  assert.equal(w.state.streams[0].stopped, 1);
  assert.equal(w.state.messagePosts.length, 0);
  assert.match(w.caption.textContent, /Tap to speak/);
});

test('a very short recording is discarded, not sent', async () => {
  const w = load();
  tap(w.mic);
  await flush(); await flush();
  w.clock.advance(100);
  tap(w.mic);
  await flush(); await flush();
  assert.equal(w.state.messagePosts.length, 0);
  assert.ok(w.mic.classList.contains('mic-btn-cancelled'));
  w.clock.advance(1000);
  assert.match(w.caption.textContent, /Tap to speak/);
});

test('mic permission denied: error message, back to idle, nothing sent', async () => {
  const w = load({ micFails: true });
  tap(w.mic);
  await flush(); await flush();
  assert.equal(w.state.messagePosts.length, 0);
  assert.match(w.caption.textContent, /Tap to speak/);
  assert.ok(w.messages().some((m) => m.classes.has('error')));
});

test('a recorder that fails to start: error message, mic released, back to idle (not stuck on connecting)', async () => {
  const w = load({ recorderFails: true });
  tap(w.mic);
  await flush(); await flush();
  assert.equal(w.state.messagePosts.length, 0);
  assert.equal(w.state.streams[0].stopped, 1);
  assert.equal(w.mic.classList.contains('mic-btn-starting'), false);
  assert.match(w.caption.textContent, /Tap to speak/);
  assert.ok(w.messages().some((m) => m.classes.has('error')));
  tap(w.mic); // and the mic still works for another try
  await flush(); await flush();
  assert.equal(w.state.getUserMediaCalls, 2);
});

test("the citizen's own recording shows as a playable voice note; the speech text is not shown", async () => {
  const w = load();
  tap(w.mic);
  await flush(); await flush();
  w.clock.advance(4000);
  tap(w.mic);
  await flush(); await flush();
  const citizen = w.messages().filter((m) => m.classes.has('citizen'));
  assert.equal(citizen.length, 1);
  assert.ok(citizen[0].firstChild.classes.has('voice-note-mine'), 'voice-note player in the citizen bubble');
  assert.equal(citizen[0].textContent.includes('नमस्ते'), false, 'transcript (mock returns नमस्ते) is not displayed');
  assert.match(citizen[0].textContent, /0:04/);
});

test('if the browser cannot make a URL for the recording, the transcript is shown instead', async () => {
  const w = load({ blobUrls: false });
  tap(w.mic);
  await flush(); await flush();
  w.clock.advance(2000);
  tap(w.mic);
  await flush(); await flush();
  const citizen = w.messages().filter((m) => m.classes.has('citizen'));
  assert.equal(citizen[0].textContent, 'नमस्ते');
});

test('press-and-hold events no longer start a recording', () => {
  const w = load();
  w.mic.dispatch('pointerdown');
  w.mic.dispatch('pointerup');
  assert.equal(w.state.getUserMediaCalls, 0);
});

test('can record again after a finished recording', async () => {
  const w = load();
  for (let i = 0; i < 2; i += 1) {
    tap(w.mic);
    await flush(); await flush();
    w.clock.advance(1500);
    tap(w.mic);
    await flush(); await flush();
  }
  assert.equal(w.state.messagePosts.length, 2);
});
