# T52 — Brief for the new UI/UX Designer + Developer: Citizen Website Redesign

This is the onboarding + task brief for whoever picks up T52. Hand this file to them as-is — it's
written to stand alone. Spec/plan for their own work is theirs to write once they've read this and
`docs/PROJECT.md`; this document is the "what and why," not a line-by-line implementation plan.

---

## Who we are, what you're joining

**Samadhan** is a voice-first AI chatbot for citizen grievances in Madhya Pradesh, built for the
MPOnline Idea & Innovation Hackathon 2026. A citizen speaks or types a complaint (Hindi/Hinglish) →
the AI asks only for missing details → the citizen confirms → a ticket is created and routed to the
correct department + ward office → the citizen can check status later. Officers manage tickets on a
separate dashboard (not your concern here).

**Read `docs/PROJECT.md` in full before anything else.** It's the actual source of truth for scope,
rules, and the Definition of Done. `docs/ONBOARDING.md` is a faster orientation if you want the
short version first.

**Your mission:** redesign and rebuild the citizen-facing website (`frontend/`) to feel modern,
trustworthy, and immediately usable by rural/village users across Madhya Pradesh — many with
limited literacy, limited smartphone experience, and Hindi (not English) as their only working
language. The current version works and is fully wired to a real backend, but it was built
function-first by a backend-focused team under deadline pressure — visual and interaction design
were never the focus. That's now your job.

## What already exists and must not change

The backend is real, live, and already tested — you are a pure frontend consumer of it, not
rebuilding any of it:

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /api/v1/message` | One citizen turn | `multipart/form-data`: `session_id`, `message_id`, and **exactly one** of `text` / `audio` / (`lat`+`lng`). Text and audio can never be sent together in the same request — that's a hard rule (S01 D-A1), not a current limitation to design around |
| `GET /api/v1/status/{complaint_id}` | Status lookup | Read-only, 4 fields back |
| `POST /api/v1/speak` | Text-to-speech | Send `{"text": "..."}`, get back `{"audio_base64": "..."}` (a WAV) — this is how the bot's replies can be *heard*, not just read |

Accepted audio types: `webm`, `ogg`, `mp4`, `wav` (whatever the browser's `MediaRecorder` produces
natively — no conversion needed or wanted). Max 2MB per recording. Full contract:
`docs/specs/S01-api-contract.md`.

**Do not change any of the above.** If something about the contract genuinely blocks good design,
say so and ask — don't quietly work around it or invent a new field.

## The two things you were specifically asked to build

### 1. WhatsApp-style press-and-hold voice recording

The current mic button is tap-to-start, tap-again-to-stop. **Replace it with press-and-hold,
exactly like WhatsApp voice notes:**
- Press and hold the mic → recording starts immediately, with clear visual feedback (pulse,
  waveform, timer — your call, but it must be obvious recording is happening).
- Release → recording stops and sends automatically. No second tap, no confirmation step in
  between — that's the whole point of the gesture.
- A very short press (accidental tap) should cancel gracefully — do not send a near-empty audio
  clip and make the citizen wait for a confused bot reply.
- Nice-to-have if time allows, not required: WhatsApp's slide-up-to-cancel gesture while holding.

### 2. The opening greeting — exact copy, both languages

This is the first thing every citizen sees. Use this copy verbatim (don't paraphrase it):

**English:**
> Hello! I'm Samadhan.
> Please tell me about your problem, or ask me if you need information about any government
> service.
> You can **speak your message or type it**. We'll do our best to help you.

**Hindi:**
> नमस्ते! मैं समाधान हूँ।
> आप अपनी समस्या हमें बताइए, या किसी भी सरकारी सेवा से जुड़ी जानकारी चाहिए तो बेझिझक पूछिए।
> आप अपनी बात **आवाज़ में बोलकर या लिखकर** बता सकते हैं। हम आपकी सहायता करने की पूरी कोशिश करेंगे।

How you present both languages (toggle, both shown together, Hindi-primary with an English line
underneath, etc.) is your design call — just don't lose either version.

## Design direction: built for a first-time villager user, not a developer

This audience did not ask for this app — they're often talked into trying it, may never have used
a chatbot before, and may not read fluently in any language. Design for that specifically:

- **Large tap targets** — nothing smaller than ~48–56px, especially the mic button, which should
  probably be the single largest, most obvious element on the screen.
- **Icon + text together, always.** An icon alone is ambiguous to a first-time user; text alone
  excludes low-literacy users. Pair them everywhere it matters (mic, send, location, status).
- **Hindi-first, always.** English only ever appears as a secondary line under Hindi, never alone,
  never as the primary label on a button a citizen must understand to proceed.
- **High contrast, generous font sizes.** Assume outdoor sunlight glare on a cheap phone screen,
  not a designer's calibrated monitor.
- **Trust-building micro-interactions**, used sparingly — a breathing/pulsing mic button at rest, a
  satisfying confirmation animation when a ticket is created, a gentle message-arrival animation.
  The goal is "this feels alive and cared-for," not "this feels like a tech demo." Don't overdo it —
  a villager who's never used a chatbot should never feel like something broke because it moved.
- **Assume a low-end Android phone and a patchy mobile network.** Keep assets light, avoid anything
  that needs a fast connection to feel responsive. If you add images/illustrations, keep them small
  and few.
- **Voice-first as a real first-class path, not an accessory.** A citizen should be able to
  complete an entire complaint by voice alone, barely reading anything, exactly as easily as a
  citizen who prefers to type. Test both paths, not just the one that's easier to build.

## Existing constraints, please discuss before deviating

- **Current stack:** plain HTML/CSS/vanilla JS, no build step, no framework
  (`frontend/index.html`, `style.css`, `app.js`, `status.js`, `status.html`). This was a deliberate
  choice for a hackathon judged partly on "can both team members explain every line of code"
  (`docs/PROJECT.md` §9). If you believe a framework or build step is genuinely worth it, make the
  case to Lead first — don't introduce one silently.
- **Existing brand palette** (from the current hero section): navy `#0F2A4A`, accent blue
  `#2563EB`, off-white `#FBFBF8`. This palette is already used in the hackathon pitch deck too —
  there's a real consistency reason to keep it unless you have a strong replacement, not just
  inertia. Propose changes explicitly if you want them.
- **Existing safety pattern, do not regress it:** the chat has already had two real bugs fixed
  where a raw browser/network error leaked to the citizen instead of a Hindi fallback message
  (`docs/problems/T50-app-js-network-fallback.md`). Whatever you build, a citizen must never see an
  English `DOMException`, `Failed to fetch`, or similar — always a Hindi, citizen-safe message.
- **Session/message identity:** `session_id` (per browser tab, `sessionStorage`) and a fresh
  `message_id` per send are both `crypto.randomUUID()`. Keep this scheme — the backend's dedupe
  logic depends on it.

## What NOT to touch

- Anything under `backend/` — you have no reason to, and no backend ticket is in scope here.
- The dashboard (`dashboard/`) — separate audience (officers), separate ticket, not yours.
- `status.html`/`status.js` unless the redesign specifically calls for extending it to match the
  new visual language — check with Lead first if you want to touch it.

## Deliverables

1. Updated `frontend/` implementing the redesign — press-and-hold recording, the new greeting, and
   the overall villager-friendly visual/interaction direction above.
2. A short written rationale (a few paragraphs is enough) explaining your key decisions —
   especially the recording gesture and any villager-specific choices that aren't obvious from the
   screen alone.
3. **Real-device testing**, not just desktop Chrome DevTools' mobile emulation — at least one actual
   low/mid-range Android phone, on a throttled or real mobile connection if possible.

## Acceptance — what "done" looks like

- [ ] Press-and-hold works exactly like WhatsApp: hold = record, release = send, a very short tap
      cancels gracefully instead of sending near-empty audio.
- [ ] The greeting shows both the English and Hindi copy above, verbatim.
- [ ] A citizen can complete a full complaint (issue → location → confirm → ticket) using **only**
      voice, and separately using **only** typing, without either path feeling like an afterthought.
- [ ] Every existing flow still works end-to-end against the real backend: text send, voice send,
      GPS location button, the 🔊 listen button on bot replies, the status-check page.
- [ ] No backend file changed; the API contract (`docs/specs/S01-api-contract.md`) is untouched.
- [ ] No raw browser/JS error is ever shown to a citizen, under any failure condition you test.
- [ ] Verified on a real Android device, not only desktop.

## Timeline — flagged, not assumed

The hackathon submission deadline is **30 Sep, noon** (`docs/PROJECT.md` §1), with a hard freeze on
product changes after that until the event ends 10 Oct. **This brief does not assume this redesign
happens before that deadline** — that's Lead's call to make explicitly with you, based on how much
runway is actually left when you start. Confirm scope/timeline with Lead before committing to a
"before submission" vs. "roadmap, after the freeze lifts" plan — don't guess.

## Questions? Don't guess.

`docs/PROJECT.md` §9, rule 2: "Never invent business rules. If a spec is unclear, stop and ask."
That applies to you too. If anything here is ambiguous — the exact recording gesture details, how
much of the visual language to keep vs. replace, whether a framework is really worth it — ask Lead
directly rather than guessing and building the wrong thing.
