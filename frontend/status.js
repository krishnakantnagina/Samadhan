// Samadhan status-check page — T22. Talks only to GET /api/v1/status/{complaint_id} (S01 section 5,
// S11). Read-only: never calls POST /api/v1/message, never touches the DB directly (S15 RULES §2).

const API_BASE = window.SAMADHAN_API_BASE || 'http://localhost:8000'; // config.js, S22

const COMPLAINT_ID_PATTERN = /^SMD-\d{4,}$/;
const GENERIC_ERROR = 'सर्वर से संपर्क नहीं हो सका। कृपया दोबारा प्रयास करें।';

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
  let response;
  try {
    response = await fetch(`${API_BASE}/api/v1/status/${encodeURIComponent(complaintId)}`);
  } catch {
    // fetch() itself throws on a network/CORS failure with the browser's own English message
    // (e.g. "Failed to fetch") -- never let that reach the citizen; always show GENERIC_ERROR.
    throw new Error(GENERIC_ERROR);
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(GENERIC_ERROR);
  }
  if (!response.ok) {
    // S01 section 7 / S15 ERRORS: every non-2xx body includes error_code, message, reply_text,
    // and request_id (backend/app/schemas.py ErrorResponse) — only reply_text is citizen-safe
    // to show as-is; the other three are for logs/support, not this page.
    throw new Error(body.reply_text || GENERIC_ERROR);
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
    renderResultError(err.message || GENERIC_ERROR);
  } finally {
    setBusy(false);
  }
}

formEl.addEventListener('submit', (event) => {
  event.preventDefault();
  checkStatus(inputEl.value);
});

// S29: the chat's ticket card links here with ?id=SMD-xxxx -- fill the box and look it up straight away.
const presetId = new URLSearchParams(location.search).get('id');
if (presetId) {
  inputEl.value = presetId;
  checkStatus(presetId);
}
