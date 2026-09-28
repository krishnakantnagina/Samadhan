You are working as **Lead** on the Samadhan project (see `CLAUDE.md` — Lead owns `frontend/`,
`dashboard/`, `specs/`, `docs/`, `submission/`; either of us can touch any file, just say so).

Your task: complete ticket **T52** — "Citizen website redesign for villagers: WhatsApp-style
press-and-hold mic, new greeting copy" (`docs/TICKETS.md`, owner "New UI/UX+dev hire" but you're
picking it up directly, depends on T29 `[x]` and T51 `[x]`).

## Read first, in order

1. `CLAUDE.md`, `docs/PROJECT.md` — team rules, scope, tech stack, the "never invent a business
   rule, ask if unclear" posture.
2. **`docs/T52-designer-brief.md` — read this in full before anything else.** It's the actual brief
   for this ticket: context, the two explicit asks (press-and-hold recording, the exact bilingual
   greeting copy), village-user design direction, constraints, deliverables, and an acceptance
   checklist. Everything below is a pointer into it, not a replacement for reading it.
3. `docs/TICKETS.md` — confirm current state before starting; T28 (cancel/restart/timeout
   end-to-end check), T30 (dashboard map), T31 (full 10-scenario integration) may or may not be
   done by the time you read this — none of them block T52, but check you're not duplicating
   something already in flight.
4. `docs/specs/S01-api-contract.md` §4.1 — the multipart contract you must not change: `text` and
   `audio` are mutually exclusive per turn (D-A1), `lat`/`lng` may be sent alone (D-A8), audio is
   one of `webm`/`ogg`/`mp4`/`wav`, ≤ 2MB.
5. `docs/specs/S16-mic-location-ui.md` — the **current** mic/location implementation you're
   replacing. Read this so you understand what already works (recording plumbing, client-side
   audio-type validation, the location-highlight-on-`ask_for` behavior) and preserve the parts of it
   that are correct — you're redesigning the *interaction* and *visuals*, not re-deriving the
   contract-level behavior from scratch.
6. `docs/specs/S17-text-to-speech.md` — the 🔊 speak-button feature (T51), already built and
   live-verified. Your redesign must keep this working; don't regress it while restyling the chat
   bubbles it lives on.
7. `frontend/app.js`, `frontend/index.html`, `frontend/style.css`, `frontend/status.js`,
   `frontend/status.html` — the current implementation, all of it. Read the whole thing before
   changing any of it; this is a redesign, not a patch, but "redesign" still means understanding
   what's there first.
8. `docs/problems/T50-app-js-network-fallback.md` — a real bug, already fixed twice (once in
   `status.js`, once in `app.js`), where a raw browser/network error leaked to the citizen instead
   of the Hindi fallback. Do not reintroduce this class of bug in whatever you rebuild.

## What to build

Everything in `docs/T52-designer-brief.md`'s "The two things you were specifically asked to build"
and "Design direction" sections. In short, so you can sanity-check scope before diving in:

- **Press-and-hold recording, exactly like WhatsApp**: hold the mic button → recording starts
  immediately with clear visual feedback; release → stops and sends automatically, no second tap;
  a very short accidental press cancels gracefully, never sends near-empty audio.
- **The exact bilingual greeting** (English + Hindi, both given verbatim in the brief) as the
  opening message.
- A villager-first visual and interaction redesign: large tap targets, icon+text pairing
  everywhere, Hindi-first with English only ever secondary, high contrast, restrained
  trust-building micro-interactions, lightweight assets for low-end phones/patchy networks, voice
  and text as genuinely equal first-class paths.

## Process — follow this repo's spec → plan → code discipline (see `docs/ONBOARDING.md`)

This is a bigger, more open-ended ticket than a typical backend one — the brief itself is closer to
a product spec than an engineering one. Still follow the same discipline the rest of this repo
uses, adapted for that:

1. Write a spec at `docs/specs/S18-citizen-ui-redesign.md` (next free number — S17 was T51's).
   Since much of "what" is already fully specified in `docs/T52-designer-brief.md`, this spec's job
   is to pin down the **concrete interaction/technical decisions** the brief deliberately left to
   you: exact recording-gesture implementation (`pointerdown`/`pointerup`/`pointercancel` vs.
   touch+mouse event pairs, the cancel-on-short-press threshold in ms, how "release outside the
   button" is handled), what changes vs. stays in `app.js`'s existing turn-handling logic
   (`postToApi`/`handleTurn` from S16 should very likely survive mostly intact — you're replacing
   the recording *trigger*, not the request/response plumbing), and how much of the existing visual
   system (colors, the hero section from T21) carries forward vs. is replaced. Use
   `docs/specs/S16-mic-location-ui.md` as a structural template (PURPOSE/SCOPE/BEHAVIOR/RULES/
   ERRORS/OUT OF SCOPE/DECISIONS/OPEN/ACCEPTANCE).
2. Write a plan at `docs/plans/T52-plan.md`, file-by-file, following `docs/plans/T51-plan.md`'s
   template (Files to create/change, Steps in order, Acceptance coverage, New libraries, How this
   doesn't regress anything already built, Verification, Not doing this turn).
3. Implement it.
4. **Verify against the real backend** (`cd backend; uv run uvicorn app.main:app --port 8000` with
   `.env` loaded), not the mock — real ASR (Sarvam/Groq Whisper), real TTS (Sarvam Bulbul), real
   Turn Engine. Specifically confirm, live:
   - Press-and-hold recording produces a real transcript exactly as the old tap-to-toggle version
     did (S16's live verification already proved the ASR pipeline works with real speech — don't
     assume the new *gesture* preserves that without checking again).
   - A short accidental press does not send audio at all.
   - The 🔊 speak button (T51) still works on the restyled bubbles.
   - The location button and its `ask_for`-triggered highlight (S16 D-S16-1) still work.
   - Text send still works, unchanged.
   - No raw browser/JS error ever reaches a chat bubble under any failure you can trigger (mic
     permission denied, geolocation denied, backend down) — this is the exact bug class in
     `docs/problems/T50-app-js-network-fallback.md`; check for it explicitly, don't assume your
     rewrite avoided it by accident.
   - Test on a real mobile viewport at minimum (Chrome DevTools device emulation is acceptable if a
     real Android device genuinely isn't available to you — say so explicitly if you substitute it,
     don't silently claim real-device testing you didn't do).
5. Tick T52 `[x]` in `docs/TICKETS.md` once verified, and update `docs/T52-designer-brief.md`'s own
   Acceptance checklist to reflect what actually got built (check the boxes that are true; if
   something in the brief turned out to be out of scope or deferred, say so there, don't just leave
   it unchecked with no explanation).
6. Commit with a clear message.

## Constraints, repeated because they matter

- Backend (`backend/`) is out of scope entirely — you have no reason to touch it. The API contract
  (`docs/specs/S01-api-contract.md`) does not change.
- `dashboard/` is a separate audience, not yours.
- Current stack is plain HTML/CSS/vanilla JS, no build step, no framework — this was deliberate
  (`docs/PROJECT.md` §9: both team members must be able to explain every line to judges). If you
  genuinely believe a framework is worth it here, say so explicitly and explain the tradeoff before
  adopting one — don't introduce one silently.
- The hackathon submission deadline is **30 Sep, noon**, with a full freeze after until 10 Oct
  (`docs/PROJECT.md` §1). Before you commit real time to this, check today's date against that
  deadline and flag — don't assume — whether this redesign is meant to land before submission or is
  post-freeze roadmap work. If it's the latter, still do the spec/plan/implementation properly, just
  don't treat it as blocking the submission checklist (`T33`–`T43`).

If anything in the brief or in S01/S16/S17 is ambiguous for this ticket, stop and ask rather than
guessing (project rule, `docs/PROJECT.md` §9, rule 2).
