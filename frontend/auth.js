// S31 -- citizen login for the chat widget: phone number + PIN/OTP, saved on the phone.
//
// Flow: the backend answers a confirmed complaint with ask_for="login" when the citizen is not logged in; the widget calls
// SamadhanAuth.showLogin(), the citizen enters a phone number and a code, a token is stored in localStorage, and the widget re-sends the
// confirmation. The token is kept (sliding expiry on the server, ~30 days idle); when it expires the backend simply asks to log in again.
// Today the code is the demo PIN (the server sends a hint, shown on screen). Real OTP needs NO change here: the same two screens, a real code.
//
// Only the chat uses this. Enquiries and status checks never need login. Nothing here logs the phone, PIN or token.

(function () {
  'use strict';

  const KEY = 'samadhan_auth'; // localStorage: { token, expires_at, phone_masked }
  const GENERIC_ERROR = 'कुछ गड़बड़ हो गई। कृपया दोबारा प्रयास करें।';
  const listeners = [];

  function apiBase() {
    return window.SAMADHAN_API_BASE || 'http://localhost:8000';
  }

  function read() {
    try {
      return JSON.parse(localStorage.getItem(KEY)) || null;
    } catch {
      return null; // storage blocked or corrupted: behave as logged out
    }
  }

  function notify() {
    const now = current();
    listeners.forEach((fn) => fn(now));
  }

  function save(auth) {
    try {
      localStorage.setItem(KEY, JSON.stringify(auth));
    } catch {
      /* private mode: the login lasts until the page closes */
      memory = auth;
    }
    notify();
  }

  let memory = null;

  function clear() {
    memory = null;
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* nothing to clear */
    }
    notify();
  }

  // The stored login if it has not expired on this phone's clock (the server decides for real; this just avoids sending a dead token).
  function current() {
    const auth = read() || memory;
    if (!auth || !auth.token) return null;
    if (auth.expires_at && Date.parse(auth.expires_at) < Date.now()) {
      try {
        localStorage.removeItem(KEY);
      } catch {
        /* ignore */
      }
      memory = null;
      return null;
    }
    return auth;
  }

  async function call(path, { body, withToken = false } = {}) {
    const headers = {};
    if (body) headers['Content-Type'] = 'application/json';
    const auth = current();
    if (withToken && auth) headers.Authorization = `Bearer ${auth.token}`;
    let response;
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 20000); // never leave the login screen waiting for ever
      try {
        response = await fetch(`${apiBase()}/api/v1${path}`, {
          method: 'POST',
          headers,
          body: body ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timer);
      }
    } catch {
      throw new Error(GENERIC_ERROR); // never show the browser's own English network message
    }
    let data = {};
    try {
      data = await response.json();
    } catch {
      /* non-JSON error: fall through to the generic text */
    }
    if (!response.ok) {
      if (data.error_code === 'AUTH_EXPIRED') clear();
      const error = new Error(data.reply_text || GENERIC_ERROR);
      error.code = data.error_code;
      throw error;
    }
    return data;
  }

  const SamadhanAuth = {
    current,
    token: () => (current() ? current().token : null),
    headers: () => (current() ? { Authorization: `Bearer ${current().token}` } : {}),
    phoneMasked: () => (current() ? current().phone_masked : null),
    onChange(fn) {
      listeners.push(fn);
      fn(current());
    },
    async start(phone) {
      return call('/auth/start', { body: { phone } }); // -> { challenge_id, provider, hint }
    },
    async verify(challengeId, code) {
      const data = await call('/auth/verify', { body: { challenge_id: challengeId, code } });
      save({ token: data.token, expires_at: data.expires_at, phone_masked: data.phone_masked });
      return data;
    },
    async logout() {
      try {
        await call('/auth/logout', { withToken: true });
      } catch {
        /* the token is dropped locally either way */
      }
      clear();
    },
    expire: clear,
    showLogin,
  };

  // --- the login screen -------------------------------------------------------------------------------------------

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (k === 'text') node.textContent = v;
      else if (k === 'class') node.className = v;
      else node.setAttribute(k, v);
    });
    children.forEach((c) => node.appendChild(c));
    return node;
  }

  // Resolves true once the citizen has logged in, false if they close the screen.
  function showLogin() {
    return new Promise((resolve) => {
      const previouslyFocused = document.activeElement;
      const overlay = el('div', { id: 'samadhan-auth-overlay' });
      const card = el('div', { class: 'samadhan-auth-card', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'samadhan-auth-title' });
      const title = el('h2', { id: 'samadhan-auth-title', text: 'लॉगिन करें · Log in' });
      const why = el('p', {
        class: 'samadhan-auth-why',
        text: 'शिकायत दर्ज करने के लिए अपना मोबाइल नंबर दें। इसी नंबर पर संबंधित अधिकारी आपसे संपर्क करेंगे।',
      });
      const privacyNote = el('p', { class: 'samadhan-auth-why' });
      privacyNote.appendChild(document.createTextNode('आपका नंबर केवल इस शिकायत के सिलसिले में अधिकारी के संपर्क के लिए रखा जाएगा। '));
      const privacyLink = el('a', { href: 'privacy.html', target: '_blank', rel: 'noopener', text: 'गोपनीयता नोटिस · Privacy notice' });
      privacyNote.appendChild(privacyLink);
      const status = el('p', { class: 'samadhan-auth-status', role: 'alert' });
      const form = el('form', { novalidate: 'novalidate' });
      const label = el('label', { for: 'samadhan-auth-input', text: 'मोबाइल नंबर (10 अंक)' });
      const row = el('div', { class: 'samadhan-auth-row' });
      const prefix = el('span', { class: 'samadhan-auth-prefix', text: '+91', 'aria-hidden': 'true' });
      const input = el('input', { id: 'samadhan-auth-input', type: 'tel', inputmode: 'numeric', autocomplete: 'tel-national', maxlength: '14', placeholder: '98765 43210' });
      row.append(prefix, input);
      const submit = el('button', { type: 'submit', class: 'samadhan-auth-primary', text: 'आगे बढ़ें' });
      const back = el('button', { type: 'button', class: 'samadhan-auth-secondary', text: 'नंबर बदलें' });
      back.hidden = true;
      const cancel = el('button', { type: 'button', class: 'samadhan-auth-secondary', text: 'अभी नहीं' });
      const actions = el('div', { class: 'samadhan-auth-actions' });
      actions.append(submit, back, cancel);
      form.append(label, row, actions);
      card.append(title, why, privacyNote, status, form);
      overlay.appendChild(card);

      let step = 'phone';
      let challengeId = null;
      let busy = false;

      function setStatus(text, isError) {
        status.textContent = text || '';
        status.classList.toggle('samadhan-auth-error', Boolean(isError));
      }
      function setBusy(on) {
        busy = on;
        submit.disabled = on;
      }
      function close(result) {
        document.removeEventListener('keydown', onKey);
        overlay.remove();
        if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
        resolve(result);
      }
      function onKey(event) {
        if (event.key === 'Escape') close(false);
      }
      function showCodeStep(hint) {
        step = 'code';
        label.textContent = 'कोड / PIN';
        prefix.hidden = true;
        input.type = 'password';
        input.inputMode = 'numeric';
        input.autocomplete = 'one-time-code';
        input.maxLength = 8;
        input.placeholder = '••••';
        input.value = '';
        submit.textContent = 'लॉगिन करें';
        back.hidden = false;
        setStatus(hint || 'आपको भेजा गया कोड दर्ज करें।', false);
        input.focus();
      }
      function showPhoneStep() {
        step = 'phone';
        label.textContent = 'मोबाइल नंबर (10 अंक)';
        prefix.hidden = false;
        input.type = 'tel';
        input.inputMode = 'numeric';
        input.autocomplete = 'tel-national';
        input.maxLength = 14;
        input.placeholder = '98765 43210';
        input.value = '';
        submit.textContent = 'आगे बढ़ें';
        back.hidden = true;
        setStatus('', false);
        input.focus();
      }

      form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (busy) return;
        const value = input.value.trim();
        if (!value) {
          setStatus(step === 'phone' ? 'कृपया मोबाइल नंबर लिखें।' : 'कृपया कोड लिखें।', true);
          return;
        }
        setBusy(true);
        setStatus('कृपया प्रतीक्षा करें…', false);
        try {
          if (step === 'phone') {
            const started = await SamadhanAuth.start(value);
            challengeId = started.challenge_id;
            showCodeStep(started.hint);
          } else {
            await SamadhanAuth.verify(challengeId, value);
            close(true);
          }
        } catch (error) {
          setStatus(error.message || GENERIC_ERROR, true);
          if (step === 'code' && error.code === 'AUTH_INVALID_CODE') input.select();
        } finally {
          setBusy(false);
        }
      });
      back.addEventListener('click', showPhoneStep);
      cancel.addEventListener('click', () => close(false));
      overlay.addEventListener('click', (event) => {
        if (event.target === overlay) close(false);
      });
      document.addEventListener('keydown', onKey);
      document.body.appendChild(overlay);
      input.focus();
    });
  }

  window.SamadhanAuth = SamadhanAuth;
})();
