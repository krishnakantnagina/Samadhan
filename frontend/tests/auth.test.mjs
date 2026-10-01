// Unit tests for frontend/auth.js token handling (Node 18+: `node --test frontend/tests`). The login screen itself is DOM-heavy and is checked in a browser.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../auth.js', import.meta.url), 'utf8');

function load({ fetchImpl, blocked = false } = {}) {
  const store = new Map();
  const localStorage = {
    getItem: (k) => { if (blocked) throw new Error('blocked'); return store.has(k) ? store.get(k) : null; },
    setItem: (k, v) => { if (blocked) throw new Error('blocked'); store.set(k, v); },
    removeItem: (k) => { if (blocked) throw new Error('blocked'); store.delete(k); },
  };
  const sandbox = { window: { SAMADHAN_API_BASE: 'http://api.test' }, localStorage, fetch: fetchImpl, Date, JSON, console };
  sandbox.window.window = sandbox.window;
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return { auth: sandbox.window.SamadhanAuth, store };
}

// objects made inside the vm sandbox have another realm's prototypes: compare them by value
const same = (actual, expected) => assert.equal(JSON.stringify(actual), JSON.stringify(expected));
const json = (status, body) => ({ ok: status < 400, status, json: async () => body });
const future = () => new Date(Date.now() + 86400000).toISOString();

test('starts logged out and sends no Authorization header', () => {
  const { auth } = load();
  assert.equal(auth.current(), null);
  same(auth.headers(), {});
});

test('verify stores the token and the header carries it; the phone is shown masked', async () => {
  const calls = [];
  const { auth, store } = load({ fetchImpl: async (url, opts) => { calls.push([url, opts]); return json(200, { token: 'tok123', expires_at: future(), phone_masked: '+91 ••••••3210' }); } });
  await auth.verify('chal-1', '5555');
  assert.equal(calls[0][0], 'http://api.test/api/v1/auth/verify');
  same(JSON.parse(calls[0][1].body), { challenge_id: 'chal-1', code: '5555' });
  same(auth.headers(), { Authorization: 'Bearer tok123' });
  assert.equal(auth.phoneMasked(), '+91 ••••••3210');
  assert.ok(JSON.parse(store.get('samadhan_auth')).token === 'tok123');
});

test('a token that expired on this phone is dropped and never sent', () => {
  const { auth, store } = load();
  store.set('samadhan_auth', JSON.stringify({ token: 'old', expires_at: new Date(Date.now() - 1000).toISOString(), phone_masked: 'x' }));
  assert.equal(auth.current(), null);
  same(auth.headers(), {});
  assert.equal(store.has('samadhan_auth'), false);
});

test('a wrong PIN shows the server message and does not log in', async () => {
  const { auth } = load({ fetchImpl: async () => json(401, { error_code: 'AUTH_INVALID_CODE', reply_text: 'कोड सही नहीं है।' }) });
  await assert.rejects(auth.verify('c', '0000'), (e) => e.message === 'कोड सही नहीं है।' && e.code === 'AUTH_INVALID_CODE');
  assert.equal(auth.current(), null);
});

test('AUTH_EXPIRED from the server clears the saved login so the citizen logs in again', async () => {
  const { auth, store } = load({ fetchImpl: async () => json(401, { error_code: 'AUTH_EXPIRED', reply_text: 'लॉगिन समाप्त' }) });
  store.set('samadhan_auth', JSON.stringify({ token: 't', expires_at: future(), phone_masked: 'x' }));
  await assert.rejects(auth.start('9876543210'));
  assert.equal(auth.current(), null);
});

test('network failures show the generic Hindi message, never the browser English text', async () => {
  const { auth } = load({ fetchImpl: async () => { throw new TypeError('Failed to fetch'); } });
  await assert.rejects(auth.start('9876543210'), (e) => /गड़बड़/.test(e.message) && !/fetch/i.test(e.message));
});

test('logout drops the token locally even when the server call fails', async () => {
  const { auth, store } = load({ fetchImpl: async () => { throw new Error('offline'); } });
  store.set('samadhan_auth', JSON.stringify({ token: 't', expires_at: future(), phone_masked: 'x' }));
  await auth.logout();
  assert.equal(auth.current(), null);
  assert.equal(store.has('samadhan_auth'), false);
});

test('listeners hear about login and logout', async () => {
  const { auth } = load({ fetchImpl: async () => json(200, { token: 't', expires_at: future(), phone_masked: '+91 ••••••3210' }) });
  const seen = [];
  auth.onChange((a) => seen.push(a ? a.phone_masked : null));
  await auth.verify('c', '5555');
  await auth.logout();
  same(seen, [null, '+91 ••••••3210', null]);
});

test('blocked storage (private mode) still works for the current page', async () => {
  const { auth } = load({ blocked: true, fetchImpl: async () => json(200, { token: 't', expires_at: future(), phone_masked: 'm' }) });
  assert.equal(auth.current(), null);
  await auth.verify('c', '5555');
  assert.equal(auth.token(), 't');
});
