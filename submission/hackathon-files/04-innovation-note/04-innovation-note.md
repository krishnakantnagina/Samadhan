# Innovation and Differentiation Note

**Samadhan (समाधान)**

## The core idea
> Understand a complaint well enough to **route** it. We do not need to transcribe a dialect perfectly.

Most complaint systems ask the citizen to do the classification (pick a department, a category, a ward). Samadhan moves that work to the
system, and keeps the AI on a short leash so it cannot make a mistake that becomes a wrong ticket.

## What is different

### 1. An AI with a hard boundary
A single LLM call returns strict JSON (intent, department, confidence, fields). **Plain code then validates every value against a service
specification file** (`specs/*.yaml`). The model can never invent a service, field, department or office: anything not in the spec is
dropped and asked again. This is enforced in code and covered by automated tests, not only by a prompt.

### 2. Adding a department is a file, not a rewrite
A new department is one YAML service spec plus its office rows. Nothing in the engine is department-specific. The prototype already runs
four departments (water, electricity, roads, sanitation) and a Human Evaluation desk on the same engine.

### 3. Honest routing instead of confident guessing
- Unsure between two departments: the bot asks "is this X or Y?" (questions written by us, not generated).
- Confident but the citizen may have meant something else: it reconfirms.
- Unknown place or confidence below 0.7: **district office, flagged `needs_review`**, never silently assigned.
- Officer corrections (reassign across departments) are written to a `routing_corrections` table, so the routing can be improved later.

### 4. Built for how people actually speak
Press-and-hold voice like a messaging app, Hindi-first copy, Hinglish and dialect-style input, spoken replies (every bot reply can be played
back; replies to a voice message play automatically), and complaint numbers understood in spoken forms (`SMD-0022`, `S M D 0 0 2 2`,
`एसएमडी शून्य शून्य दो दो`).

### 5. Resilient by design
LLM chain of three Groq models then Gemini; ASR fallback; short timeouts; citizen-safe Hindi error messages; duplicate-message protection
through a database key, so a double-tap or a network retry never creates two tickets.

### 6. Privacy by minimalism
Mobile-number login before a complaint is filed (so the officer can call back), no name stored, a status endpoint that returns only four fields (ID, status, department, updated time),
audio in a private bucket, database access closed to the public key.

## Where Samadhan sits next to what exists
MPOnline's Customer Solutions Hub is a call-centre and IVR-first platform with human agents in the loop. Samadhan is a **complementary
self-service digital channel**: no call queue, no agent step before the ticket exists, and it can reduce load on the call centre. We do not
claim it replaces the existing platform, and we have not verified any of the platform's own performance claims.

## Honest limits
Demo office data for most departments; GPS does not yet choose a ward; mobile login uses a demo PIN, not a real SMS OTP, and there is no rate limiting yet; information
questions get a link, not an answer. Dialect results come from synthetic data, not native-speaker review.
