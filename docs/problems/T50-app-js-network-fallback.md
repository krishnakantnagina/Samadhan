# Problem: `app.js` shows the raw browser error instead of the Hindi fallback on network failure

Ticket: `docs/TICKETS.md` T50 (owner Dev, depends on T21 `[x]`, done when "Backend unreachable →
Hindi message shown, not raw error"). Found: 28 Sep 2026, during T22 (status-check page) manual
verification. Affects: `frontend/app.js` (T21), the citizen chat page — the product's main flow.

## Summary

When the backend is unreachable (down, DNS failure, CORS misconfiguration, offline device), the
chat page shows the **raw English browser error** (e.g. `Failed to fetch`) instead of the Hindi,
citizen-safe fallback message it's supposed to show. This is a Hindi-first product
(`docs/PROJECT.md` §6) built for citizens who may not read English technical jargon — this is
exactly the class of failure `docs/specs/S01-api-contract.md` §7 was written to prevent for the
*backend's* error bodies (every non-2xx response carries a citizen-safe `reply_text`), but the
frontend has its own, separate path around that protection when the network call fails before a
response ever arrives.

## Root cause

`frontend/app.js`, in `sendToApi()` and `send()`:

```js
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
    throw new Error(body.reply_text || 'कुछ गड़बड़ हो गई। कृपया दोबारा प्रयास करें।');
  }
  return body;
}
...
} catch (err) {
  appendMessage('error', err.message || 'सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।');
}
```

If `fetch()` itself throws — network down, DNS failure, CORS block, offline — the browser's own
`TypeError` propagates straight into the `catch` block below with a non-empty `.message` (in
Chrome: `"Failed to fetch"`; wording differs per browser, but it's always English and always a raw
technical string). Because `err.message` is truthy, `err.message || fallback` never falls through
to the Hindi text — the citizen sees the browser's own error, verbatim.

`response.json()` has the same exposure: if the server responds but with a non-JSON or malformed
body, `.json()` throws its own `SyntaxError`, which would also leak through unfiltered.

## Evidence: this exact bug was just found and fixed in a sibling file

`frontend/status.js` (new in T22) originally had the identical `fetch()` + `err.message || fallback`
pattern, copied from `app.js` as the established house style. Manual verification for T22 (stop the
real backend, submit a lookup) reproduced this exact failure — the page showed `Failed to fetch`
instead of the Hindi retry message. It was fixed there in this session; `app.js` was **not** touched,
since T22's scope was the new status page, not an audit of the existing chat page — this ticket is
that follow-up.

## Impact

- Chat (`app.js`) is the product's primary, highest-traffic flow — more consequential than the
  status page this bug was originally caught in.
- Low-probability but real at demo time: any backend hiccup, a wrong `API_BASE`, a CORS
  misconfiguration, or a flaky venue network during judging would surface English technical jargon
  to a Hindi-speaking demo persona, undermining the "Hindi-first" pitch itself.
- No data loss, no security exposure — purely a broken error-message fallback.

## Reproduction

1. `cd backend; uv run uvicorn app.main:app --port 8000`, then stop it (or just don't start it).
2. `cd frontend; python -m http.server 5500`, open `index.html`.
3. Type any message and send it.
4. **Expected:** `सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।` (or similar Hindi text).
   **Actual:** `Failed to fetch` (or your browser's equivalent raw error).

## Suggested fix

Mirror the fix already applied and verified in `frontend/status.js`'s `fetchStatus()`: separate
"the network call itself failed" from "the server returned a body," and only ever read
`body.reply_text` from an actual HTTP response. Never let a caught exception's own `.message`
reach `appendMessage`/the citizen.

```js
const GENERIC_ERROR = 'सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।';

async function sendToApi(text) {
  const form = new FormData();
  form.append('session_id', getSessionId());
  form.append('message_id', crypto.randomUUID());
  form.append('text', text);

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
```

`send()`'s catch block can stay as `appendMessage('error', err.message || GENERIC_ERROR)` (now
always safe either way), reusing the same `GENERIC_ERROR` constant instead of the two separately
duplicated Hindi literal strings currently in the file (`sendToApi`'s own fallback and `send()`'s
catch fallback — they're worded slightly differently today; consolidating to one constant also
fixes that drift).

## Acceptance

- [ ] Backend unreachable → chat page shows `GENERIC_ERROR` (Hindi), not a raw browser/JS error string.
- [ ] Real HTTP error responses (`400`/`503`/etc. from the backend) still show their actual
      `reply_text` unchanged — no regression to existing error handling.
- [ ] Existing T21 happy-path behavior (successful message send, `ask`/`confirm`/`submitted`
      rendering) unchanged.
- [ ] `docs/TICKETS.md` T50 ticked `[x]`.

## References

- `frontend/app.js` (T21) — the file to fix.
- `frontend/status.js` (T22) — the reference implementation of this exact fix, already applied and
  manually verified (stopped backend, confirmed Hindi fallback renders).
- `docs/specs/S01-api-contract.md` §7 — the citizen-safe error principle this bug violates.
- `docs/plans/T22-plan.md` — Verification step 5, where this bug was originally found.
