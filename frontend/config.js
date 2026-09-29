// API address for the website (S22 D-S22-2). Vercel's build overwrites this file from the SAMADHAN_API_BASE env var
// (see vercel.json). No trailing slash. Locally, the API is called on the SAME host name the page was opened with, so both
// http://localhost:5500 and http://127.0.0.1:5500 work (a mismatch, or a browser that cannot resolve `localhost`, used to
// show "server unreachable").
window.SAMADHAN_API_BASE = window.SAMADHAN_API_BASE ||
  (['localhost', '127.0.0.1'].includes(location.hostname)
    ? `http://${location.hostname}:8000`
    : 'http://localhost:8000');
