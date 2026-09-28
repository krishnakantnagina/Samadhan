# Plan: T22 — Status-check page

Ticket: `docs/TICKETS.md` T22 (owner Dev, depends on T08 `[ ]` and T21 `[x]`, done when "Shows
status"). Note: T08's checkbox is unticked in `docs/TICKETS.md` even though `backend/mock/app.py`
demonstrably exists and is already relied on elsewhere (`backend/README.md`, the contract test
suite) — treated as a stale checkbox, not a blocker; not touched by this plan.
Spec: `docs/specs/S15-status-check-page.md`.

**Scope: T22 only.** Adds a second static page, `frontend/status.html` + `frontend/status.js`,
next to the existing chat page. Read-only: calls `GET /api/v1/status/{complaint_id}` (S11, already
built) and nothing else. Does not touch `backend/`, does not change the chat flow's behavior, does
not add a build step. The only edits outside the two new files are: a `style.css` addition (new
status-color badge variants + a small page-layout block), a one-line header cross-link in
`index.html`, and a one-line `API_BASE` fix in `app.js` (justified in S5).

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `frontend/status.html` | Create | The status-check page markup (S15 D-S15-1) |
| `frontend/status.js` | Create | Client validation + `GET /status/{id}` call + result rendering |
| `frontend/style.css` | Edit | New `--success-*` tokens, 3 new `.badge-*` status color variants, status-page layout classes, header cross-link style |
| `frontend/index.html` | Edit | One-line header link to `status.html` (resolves S15 G-S15-2) |
| `frontend/app.js` | Edit | `API_BASE` `:8001` → `:8000` (resolves S15 G-S15-1 — see S5) |
| `docs/TICKETS.md` | Edit (last step) | Tick T22 `[x]` |

## 2. Steps, in order

**S1 — `frontend/status.html`.**
Same page-shell convention as `index.html` (`.app-shell` + `.app-header`), no `.hero` block — this
is a small utility page, not a landing page.

```html
<!doctype html>
<html lang="hi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>समाधान — शिकायत की स्थिति</title>
<link rel="stylesheet" href="style.css">
</head>
<body>

<div class="app-shell">
<header class="app-header">
  <h1>समाधान</h1>
  <p class="tagline">अपनी शिकायत की स्थिति जानें</p>
</header>

<main class="status-main">
  <form id="lookup-form" class="status-form">
    <label for="complaint-id" class="status-label">शिकायत क्रमांक</label>
    <input id="complaint-id" class="input" type="text" placeholder="SMD-0042" autocomplete="off" required>
    <div id="form-error" class="form-error" role="alert" hidden></div>
    <button type="submit" id="btn-check" class="send-btn status-submit">स्थिति देखें</button>
  </form>

  <div id="result" class="status-result" aria-live="polite"></div>

  <a href="index.html" class="chip-btn status-back">&larr; बातचीत पर वापस जाएँ</a>
</main>
</div>

<script src="status.js"></script>
</body>
</html>
```

Reuses `.input`/`.send-btn`/`.chip-btn` exactly as `index.html`/`app.js` already define them — no
new form-control styling invented (S15 RULES §4).

**S2 — `frontend/status.js`.**
Mirrors `app.js`'s helper style: small named functions, a `setBusy` disable-while-loading toggle,
try/catch around `fetch` with a citizen-safe fallback string, `createElement`/`textContent` only —
nothing from the network (`department`, `status`, `updated_at`, the error body's `reply_text`) is
ever put through `innerHTML`, since all of it is untrusted server/DB content reaching the DOM.

```js
// Samadhan status-check page — T22. Talks only to GET /api/v1/status/{complaint_id} (S01 section 5,
// S11). Read-only: never calls POST /api/v1/message, never touches the DB directly (S15 RULES §2).

const API_BASE = 'http://localhost:8000';

const COMPLAINT_ID_PATTERN = /^SMD-\d{4,}$/;

// Hindi status labels (S15 D-S15-3). needs_review's text matches app.js's existing badge copy
// (line 73) exactly; new/in_progress/resolved are PROPOSED, unconfirmed with Lead (S15 G-S15-3).
const STATUS_LABELS = {
  new: 'नई शिकायत',
  in_progress: 'कार्यवाही जारी है',
  resolved: 'समाधान हो गया',
  needs_review: 'समीक्षा के लिए भेजा गया',
};

const formEl = document.getElementById('lookup-form');
const inputEl = document.getElementById('complaint-id');
const errorEl = document.getElementById('form-error');
const submitBtn = document.getElementById('btn-check');
const resultEl = document.getElementById('result');

function setBusy(busy) {
  inputEl.disabled = busy;
  submitBtn.disabled = busy;
}

function showFormError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function clearFormError() {
  errorEl.textContent = '';
  errorEl.hidden = true;
}

function clearResult() {
  resultEl.textContent = '';
}

function formatUpdatedAt(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso; // fallback: show the raw value rather than crash
  return date.toLocaleString('hi-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

function renderStatusCard(data) {
  // Reuses .card-ticket as-is (same id/rows/badge shape as app.js's appendTicketCard) — S15
  // RULES §4: new classes follow existing naming; this needs no new card modifier at all.
  const card = document.createElement('div');
  card.className = 'card card-ticket';

  const id = document.createElement('div');
  id.className = 'complaint-id';
  id.textContent = data.complaint_id;
  card.appendChild(id);

  const dept = document.createElement('div');
  dept.className = 'ticket-row';
  dept.textContent = `विभाग: ${data.department}`;
  card.appendChild(dept);

  const updated = document.createElement('div');
  updated.className = 'ticket-row';
  updated.textContent = `अंतिम अपडेट: ${formatUpdatedAt(data.updated_at)}`;
  card.appendChild(updated);

  const badge = document.createElement('div');
  badge.className = `badge badge-${data.status}`;
  badge.textContent = STATUS_LABELS[data.status] || data.status;
  card.appendChild(badge);

  resultEl.appendChild(card);
}

function renderResultError(message) {
  const el = document.createElement('div');
  el.className = 'msg error';
  el.textContent = message;
  resultEl.appendChild(el);
}

async function fetchStatus(complaintId) {
  const response = await fetch(`${API_BASE}/api/v1/status/${encodeURIComponent(complaintId)}`);
  const body = await response.json();
  if (!response.ok) {
    // S01 section 7 / S15 ERRORS: every non-2xx body includes error_code, message, reply_text,
    // and request_id (backend/app/schemas.py ErrorResponse) — only reply_text is citizen-safe
    // to show as-is; the other three are for logs/support, not this page.
    throw new Error(body.reply_text || 'सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।');
  }
  return body;
}

async function checkStatus(rawId) {
  const complaintId = rawId.trim();
  clearFormError();
  clearResult();

  if (!complaintId) {
    showFormError('कृपया शिकायत क्रमांक डालें।');
    return;
  }
  if (!COMPLAINT_ID_PATTERN.test(complaintId)) {
    // S15 ERRORS table's own example text.
    showFormError('सही शिकायत क्रमांक डालें (जैसे SMD-0042)');
    return;
  }

  setBusy(true);
  try {
    const data = await fetchStatus(complaintId);
    renderStatusCard(data);
  } catch (err) {
    renderResultError(err.message || 'सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।');
  } finally {
    setBusy(false);
  }
}

formEl.addEventListener('submit', (event) => {
  event.preventDefault();
  checkStatus(inputEl.value);
});
```

Covers S15 BEHAVIOR §1–6 and the ERRORS table exactly: empty vs. malformed input get distinct
inline messages and neither ever calls `fetchStatus` (both guards run before any request); `400`/
`404` show the server's `reply_text` verbatim; network failure / non-JSON / `5xx` fall through to
the same generic Hindi retry line `app.js`'s own `send()` catch block already uses, for consistency.
One-shot per submit — no timers, no polling (S15 D-S15-4).

**S3 — `frontend/style.css` edits.**

(a) Extend the existing `:root` block (lines 3–19) with two success tokens, right after the
existing `--ticket-border: #c7d9f0;` (line 18), following the same 3-variable shape `--error-*`
already uses (lines 12–14):
```css
  --success-bg: #ecfdf5;
  --success-border: #86efac;
  --success-text: #166534;
```

(b) Add three badge color variants right after the existing `.badge` rule (lines 160–170).
`needs_review` needs **no new rule** — the base `.badge` is already the orange treatment `app.js`
uses for it (S15 OUT OF SCOPE: "reuse, don't redesign"); `status.js` still adds a
`badge-needs_review` class to the element for symmetry, it just matches no selector and falls
through to `.badge`'s existing defaults.
```css
.badge-new {
  background: #f1f5f9;
  color: var(--muted);
  border: 1px solid var(--bot-border);
}

.badge-in_progress {
  background: var(--ticket-bg);
  color: var(--accent);
  border: 1px solid var(--ticket-border);
}

.badge-resolved {
  background: var(--success-bg);
  color: var(--success-text);
  border: 1px solid var(--success-border);
}
```
All three reuse existing tokens (`--muted`, `--bot-border`, `--ticket-bg`/`--ticket-border`,
`--accent`) except `--success-*`, the one new semantic pair this ticket adds — same structural
shape as `--error-*`, not an arbitrary new color.

(c) Append a status-page layout block near the end of the file (after the Hero section, as its own
clearly-labeled block, matching the existing `/* --- Hero section --- */` comment convention at
line 248):
```css
/* ---------------------------------------------------------------------------
   Status-check page (T22) — reuses .card/.card-ticket/.badge/.input/.send-btn/.chip-btn above.
--------------------------------------------------------------------------- */

.status-main {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.status-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--bot-text);
}

.form-error {
  font-size: 14px;
  color: var(--error-text);
  background: var(--error-bg);
  border: 1px solid var(--error-border);
  border-radius: 10px;
  padding: 8px 12px;
}

.status-submit {
  width: 100%;
}

.status-result .card {
  margin-top: 0;
}

.status-back {
  align-self: flex-start;
  text-decoration: none;
}
```

(d) Add one small style for the header cross-link, next to the existing `.app-header .tagline` rule
(lines 51–55):
```css
.app-header .header-link {
  display: inline-block;
  margin-top: 8px;
  font-size: 13px;
  color: #c7d9f0;
  text-decoration: underline;
}
```

**S4 — `frontend/index.html` edit.**
One line inside the existing `.app-header` block (lines 50–53), right after the `.tagline`
paragraph:
```html
<header class="app-header">
  <h1>समाधान</h1>
  <p class="tagline">अपनी पानी की समस्या यहाँ बताइए</p>
  <a href="status.html" class="header-link">अपनी शिकायत की स्थिति जानें</a>
</header>
```
No JS needed — a plain link. This resolves S15's G-S15-2 as a header link, not a post-`submitted`
prefilled query-param handoff (that would need `status.js` to read a query string, which is more
than T22's done-when asks for).

**S5 — `frontend/app.js` edit: `API_BASE`.**
Current (lines 4–5):
```js
// Point this at the mock (T08) today; switch to :8000 once T18 ships the real /message route.
const API_BASE = 'http://localhost:8001';
```
Change to:
```js
// Real backend (T18 shipped the real /message route; matches status.js's API_BASE, S15 G-S15-1).
const API_BASE = 'http://localhost:8000';
```
Justification: `docs/TICKETS.md` shows T18 (real `/message`) and T19 (real `/status`) both `[x]` —
done, and `docs/ONBOARDING.md`'s own "Run it locally" section documents the real backend on `:8000`
and the mock separately on `:8001`, matching this change. Leaving `app.js` on the mock while
`status.js` points at the real backend would mean a ticket the chat page creates couldn't be found
by the status page (different backing stores — the mock has no real DB) — confusing in any manual
run or demo that uses both pages together. `backend/README.md` is stale on this point (still framed
around T07, before T18/T19 shipped) and is not touched by this plan; a developer who wants the mock
locally can still point either constant back to `:8001`.

**S6 — Manual smoke test, then tick it off.**
Run the Verification steps below against real seeded/dashboard data. Once they pass, tick T22 in
`docs/TICKETS.md`.

## 3. Acceptance coverage

| S15 acceptance item | Satisfied by (code) | Verified by |
|---|---|---|
| Valid, existing complaint ID → status, department, updated time shown | S2 `renderStatusCard` | Verification step 2 |
| Malformed ID → inline error, no request | S2 `checkStatus` guards (regex test before any `fetch`) | Verification step 3 |
| Unknown but well-formed ID → citizen-safe "not found" message | S2 `fetchStatus` (`body.reply_text` on non-2xx) | Verification step 4 |
| Scenario 9 (officer sets "In progress" → page shows `in_progress`) | Trivially true — this page only reads (S2 `fetchStatus`) once T24 has written `tickets.status` | Verification step 2, using a ticket whose status was changed via the dashboard |
| No fields beyond the endpoint's four are ever displayed | S2 `renderStatusCard` only reads `complaint_id`/`department`/`updated_at`/`status` off `data` | Code inspection — `data` is the parsed `StatusResponse` body, nothing else is read |

## 4. New libraries
None. Plain HTML/CSS/JS, no build step — matches T21's existing pattern.

## 5. How this doesn't regress T19, T21, or T23/T24
- No file under `backend/` changes; `GET /status/{complaint_id}` (S11/T19) is called exactly as
  documented — nothing about its request/response shape is assumed beyond `StatusResponse`'s four
  fields and `ErrorResponse`'s `reply_text`.
- `index.html`'s only change is one additive `<a>` line inside `.app-header`; `#chat`, `#composer`,
  and all of `app.js`'s existing event wiring are untouched. The `API_BASE` edit (S5) only changes
  *which* backend the chat page talks to, not any request/response handling logic — T21's flow is
  otherwise byte-for-byte the same.
- `style.css`'s edits are additive (`:root` gains 2 new variables, 3 new `.badge-*` selectors, a
  new `.status-*` block); no existing selector's rules are modified, so `.hero`/`.card-summary`/
  `.card-ticket`/`.msg`/`.composer` etc. render exactly as they did after T21.
- Nothing here touches `dashboard/` (T23/T24) — the dashboard's own status-change UI is unaffected;
  this page merely reflects whatever the dashboard already wrote to `tickets.status`.

## Verification
1. Start the real backend: `cd backend; uv run uvicorn app.main:app --port 8000` (needs
   `ALLOWED_ORIGINS` in `.env` to include `http://localhost:5500`, already documented in
   `.env.example`).
2. From `frontend/`: `python -m http.server 5500`, open `http://localhost:5500/status.html`.
   Enter a real seeded complaint ID (find one via the dashboard's "All Tickets" list — T20's 15
   seeded rows) whose status is `new`; confirm complaint ID, department, formatted update time, and
   Hindi status badge all render correctly. Repeat with a ticket whose status was changed to
   `in_progress` via the T24 dashboard, to cover Scenario 9.
3. Enter a malformed ID (e.g. `SMD-12`, `abc`, empty) — confirm the inline Hindi error appears and,
   via browser dev tools' Network tab, confirm no request was sent to `/api/v1/status/...`.
4. Enter a well-formed but non-existent ID (e.g. `SMD-9999`) — confirm the citizen-safe "not found"
   `reply_text` from the `404 COMPLAINT_NOT_FOUND` body is shown.
5. Stop the backend (Ctrl-C the uvicorn process) and submit a valid-looking ID — confirm the
   generic Hindi retry fallback message appears (network failure path), not a raw JS error.
6. On `index.html`, confirm the new header link navigates to `status.html`; on `status.html`,
   confirm "← बातचीत पर वापस जाएँ" navigates back to `index.html`.
7. Load `index.html` and confirm the chat flow still works end-to-end against the real backend
   (S5's `API_BASE` change) — send one message, confirm a reply renders, matching T21's existing
   smoke test.
8. (Defense in depth, not a new manual step) The `400 INVALID_COMPLAINT_ID` path is already covered
   by `backend/tests/test_routes.py` (T19) and is unreachable from this UI by design, since client
   validation runs first.

## Not doing in this turn
- Auto-refresh or polling (S15 D-S15-4 / OUT OF SCOPE).
- Any change to the `GET /status` endpoint or anything under `backend/` (already built, S11/T19).
- Redesigning how `needs_review` looks — kept identical to `app.js`'s existing badge (S15 OUT OF
  SCOPE); only its 3 siblings (`new`/`in_progress`/`resolved`) get new colors.
- Confirming the exact Hindi copy for `new`/`in_progress`/`resolved` status labels with Lead — the
  three added here (S2) are PROPOSED, same open item S15 already flagged (G-S15-3); `needs_review`'s
  text has real precedent (`app.js` line 73) and is not open.
- Prefilling `status.html` from a `submitted` ticket's `complaint_id` via query param, or any other
  richer chat↔status handoff — S15 G-S15-2 is resolved here as a plain header link only, per the
  already-confirmed decision; a query-param prefill is a possible future enhancement, not in scope.
- Automated frontend tests — no test framework exists anywhere in `frontend/` (confirmed: no
  `frontend/tests`, no `package.json`, no Playwright/Cypress); this plan relies on the manual
  Verification section above, same posture as T19/T23/T24.
- Updating `backend/README.md`'s stale T07-era framing or its mock/real port instructions — out of
  scope for a frontend ticket; noted in S5 but not fixed here.
