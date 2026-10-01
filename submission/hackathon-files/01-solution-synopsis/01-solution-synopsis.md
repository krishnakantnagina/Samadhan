# Samadhan (समाधान): Solution Synopsis

**MPOnline Idea & Innovation Hackathon 2026 · Problem Statement 5 · Pilot city: Bhopal**
Repository: https://github.com/krishnakantnagina/Samadhan (tag `v1-mvp`) · Live URL: https://samadhan-web.onrender.com/

## The problem
A citizen with a civic problem (no water, a broken road, uncollected garbage) has to know which department owns it, which zone or
ward office to approach, and how to fill in a form or navigate a menu. Many citizens speak Hindi, Hinglish or a local dialect and would
rather talk than type. A wrongly routed complaint loses days.

## The solution
Samadhan is a **voice-first AI chatbot website**. The citizen speaks or types a complaint in Hindi or Hinglish. Samadhan:

1. works out what kind of message it is: a complaint, an information question, a status question, or out of context;
2. picks the right **department** (water, electricity, roads, sanitation, or a general triage desk);
3. asks only for what is missing (usually the issue, then the location), then asks the citizen to **confirm**;
4. files a ticket **`SMD-xxxx`** and routes it to the correct **ward office**, or to the district office marked `needs_review` when unsure;
5. lets the citizen check status by complaint number, typed or spoken, in the chat or on a status page.

Officers work on a **dashboard**: department-wise open counts, filters, ticket detail with the original audio, status changes,
reassignment across departments with an audit trail, a review queue for low-confidence tickets, and a map.

## What makes it trustworthy
The AI never has the last word. One LLM call proposes the intent, department and fields; **plain code validates every value against a
service specification file** before anything is stored. The model cannot invent a department, field or office. Information questions
get a fixed honest reply, a validated `.gov.in` link and a disclaimer, not a made-up answer. Citizen sessions are anonymous and the
status endpoint returns only four fields.

## Where it stands (measured, not estimated)
- Routing: about **90% exact** on 60 test messages (26 hand-written, 34 synthetic Bundeli/Malvi). One run each; synthetic data written by an LLM.
- **415 backend and 35 dashboard automated tests pass.**
- Voice in (Sarvam, Groq Whisper fallback), voice replies (Sarvam Bulbul), GPS, LLM fallback chain (three Groq models, then Gemini).
- Honest limits: electricity, roads, sanitation and general-triage office data are **DEMO**; ward names are unverified; GPS does not yet
  pick a ward; there is no citizen phone verification and no rate limit yet (see the roadmap).

## Next
Verified ward and office data, phone-verified complaints (an SMS OTP was tested successfully on a real number), rate limiting, then
integration with MPOnline's existing channels.
