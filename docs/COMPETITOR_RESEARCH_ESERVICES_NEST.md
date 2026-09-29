# Competitor Research — eServicesNest / CustomerSolutionsHub

Research target: `https://eservicesnest.com/CustomerSolutionsHub`. Compared against Samadhan as it
actually stands today (specs in `docs/specs/`, `docs/PROJECT.md`, `docs/TICKETS.md`), not an
idealized future version of Samadhan.

**Read this first — the single most important finding:** this page is not a random competitor. It is
a marketing/pitch microsite for a **Call Centre / "Customer Solutions Hub" AI citizen-engagement
platform run by MPOnline Limited** — the Government of Madhya Pradesh & TCS joint venture. MPOnline
Limited is the exact organizing body of Samadhan's own hackathon (`docs/PROJECT.md` line 12: "MPOnline
Idea & Innovation Hackathon 2026, Problem Statement 5"). This isn't an outside company competing for
the same government contract — **it's the hackathon organizer's own existing platform**, most likely
built by/with TCS and pitched to *other* Madhya Pradesh government departments as a service they can
subscribe to. That context should shape how the team frames Samadhan's pitch (see §14 and the Final
Team-Lead Report): as complementary to an existing voice/IVR call-centre channel, not as a head-to-head
replacement for a system the judges' own parent organization already operates.

An initial research pass used `WebFetch` (non-JS-rendering) and returned almost nothing — the site is
a client-rendered single-page app, so a non-browser fetch only sees a bare `<title>`. Re-running the
research through an actual browser (`mcp__claude-in-chrome`, which executes JavaScript) surfaced the
real page content in full. That render is the primary source for this document; a handful of
sub-tabs on one interactive widget (§6) could not be clicked through before the page became
unresponsive to further automation and is honestly marked unverified rather than guessed at.

Labels used throughout, matching this repo's own `VERIFIED`/`DEMO`/`NOT FOUND` convention:
**Verified Fact** (the rendered page states this, or it's directly corroborated by Samadhan's own
`PROJECT.md`; source cited) · **Competitor Claim** (their own marketing copy — a performance number,
quality claim, or benefit statement that is *displayed* as Verified Fact but is **not** independently
confirmed to be true) · **Technical Inference** (a reasonable guess at how a described capability is
*likely* built, explicitly not confirmed) · **Unknown/Unverified** (looked, found nothing, or ran out
of ability to look further).

---

## 1. Executive Summary

`eservicesnest.com/CustomerSolutionsHub` is a single-page marketing site for **"Customer Solutions
Hub — Call Centre"**, an AI-enabled, omnichannel citizen-engagement platform operated by **MPOnline
Limited** (a Government of Madhya Pradesh & TCS joint venture) and pitched to *other* MP government
departments as a service to adopt (Verified Fact: page content, `https://eservicesnest.com/
CustomerSolutionsHub`). MPOnline Limited is also the organization running Samadhan's hackathon
(Verified Fact: `docs/PROJECT.md` line 12).

The page is explicit marketing/sales copy aimed at government department decision-makers ("Partner
with the Customer Solutions Hub... Transform your department's citizen service delivery"), not a
technical spec. It describes a **voice-first, call-centre-centric** platform (IVR, "Dialer,"
"Incoming Voice Agent," live-call metrics) with AI layered on top of a traditional contact-centre
operation — a materially different channel emphasis from Samadhan's **website/chat-first** design.
Performance numbers (80% of calls answered in 20s, 24×7 availability), the "zero government
investment" franchise/revenue-share business model, and the list of "AI Capabilities" tabs are all
**Competitor Claims**: real marketing statements, not independently verified figures or confirmed
architecture. No specific technology vendor (ASR provider, LLM, CRM product, telephony platform) is
named anywhere on the page — only category labels ("IVR Platform," "AI Engine," "CRM Integration").

No client department names, case studies, or press coverage were found for this specific platform in
web search, and one interactive widget (§6, the 7-tab "AI Capabilities" section) could only be read
for its default tab before the page stopped responding to further automated clicks — those other six
capability names are confirmed, their descriptions are not.

**Recommendation:** treat this less as "a competitor to beat" and more as "the ecosystem Samadhan's
pitch must position itself against." See §14 and the Final Team-Lead Report for what that implies.

---

## 2. Competitor Overview

| Item | Status |
|---|---|
| Domain | `eservicesnest.com` — resolves; client-rendered SPA (Verified Fact: renders fully in a JS-executing browser, returns only a bare title to a non-JS fetch) |
| Product name | "Customer Solutions Hub" / "Call Centre" (Verified Fact: page headings, footer: *"Customer Solutions Hub - , A Joint Venture of Government of Madhya Pradesh & TCS"*) |
| Operating company | **MPOnline Limited** (Verified Fact: page states "MPOnline Limited is a Joint Venture between the Government of Madhya Pradesh and TCS"; contact block lists `helpdesk@mponline.gov.in`, `0755-6720222`, "MPOnline Limited, Madhya Pradesh") |
| Relationship to Samadhan's hackathon | **Same organizing body.** MPOnline runs "MPOnline Idea & Innovation Hackathon 2026" per Samadhan's own `docs/PROJECT.md` (Verified Fact, cross-referenced from our own repo) |
| Government/technology partnerships | Government of Madhya Pradesh + TCS (Tata Consultancy Services), stated directly (Verified Fact). No other named technology vendor (ASR/LLM/CRM/telephony product) anywhere on the page |
| Geography / state | Madhya Pradesh, India (Verified Fact) |
| Product category | A **call-centre / IVR-first** citizen engagement platform with AI layered on top, marketed for adoption by other MP government departments — not a self-service chatbot website like Samadhan (Verified Fact: page framing, "Call Centre" breadcrumb, "Dialer," "Incoming Voice Agent") |
| Public case studies | None found — page describes capabilities and benefits in the abstract, no named client department currently live on the platform, no user testimonials |
| Business model shown | "Zero upfront Government investment" + citizen-paid portal fee + CSC/kiosk franchise network with a 40–60% revenue split (Competitor Claim — see §10) |

---

## 3. Verified Capabilities

What the rendered page actually states it offers (Verified Fact: page content, all from
`https://eservicesnest.com/CustomerSolutionsHub`), each capability's *substance* still a Competitor
Claim unless otherwise noted:

| Area | What the page states |
|---|---|
| Channels | "Omnichannel Contact Center" across "voice, digital, and assisted channels" |
| Call handling | IVR Platform, Dialer, live call volume/pattern monitoring |
| AI — speech | Speech-to-Text (STT), Contextual Summarization, Intent & Sentiment Detection ("AI Speech Intelligence" tab, the one tab whose detail was actually read — see §6) |
| AI — other named capabilities (names only, detail unread) | Grievance Intelligence, Proactive Outreach, Incoming Voice Agent, Knowledge Assistant, Agent Assist, Predictive Analytics |
| CRM/ticketing | "CRM Integration," "Ticketing Platform" (named as components, no product/vendor identified) |
| Knowledge management | "Knowledge Management System" (named component; "Knowledge Assistant" also appears as a separate AI-tab name — likely related, not confirmed to be the same thing) |
| Authority dashboard | "Executive Dashboard for Government Authorities": Live Calls, Pending Complaints, Resolution Rate, SLA, District-wise Trends, Department-wise Issues, Heat Maps, Sentiment Dashboard, AI Insights, Citizen Satisfaction |
| Infrastructure | "API Gateway," "Integration Layer," "Secure Infrastructure," "Disaster Recovery" (named, no detail) |
| Deployment | "Flexible deployment (On-Premise, Cloud, Hybrid)" |
| Multilingual | Listed only as a **future roadmap item** ("Multilingual Expansion... serving Madhya Pradesh's diverse linguistic communities"), i.e. **not yet claimed as a current capability** — a notable and specific admission for a document like this |

None of these are backed by a demo, screenshot, technical whitepaper, or named client on the page. They
are the platform's own stated capability list, not confirmed working features.

---

## 4. Real-World Implementation Evidence

No case study, named government department currently live on the platform, press release, tender
document, or third-party review was found (Unknown/Unverified — web search for the platform name,
"CustomerSolutionsHub," and MPOnline-call-centre combinations returned nothing beyond the site
itself). The page's own language is forward/aspirational and sales-oriented ("Partner with the
Customer Solutions Hub," "Transform your department's citizen service delivery") rather than
retrospective/case-study oriented ("here's what we did for Department X") — **Technical Inference**:
this reads like a platform being actively pitched for adoption, not one with a public track record yet,
though it could also simply be that any live deployments aren't publicized. Both are consistent with
what's visible; neither is confirmed.

---

## 5. Architecture/Workflow Analysis

The page names components but never describes how they connect end-to-end, so the workflow below is
**Technical Inference** (a reasonable reconstruction from the named pieces, not a confirmed
architecture):

```
Citizen (phone call, primary channel) → IVR / Dialer → (if AI-routed) Incoming Voice Agent →
Speech-to-Text → Contextual Summarization + Intent & Sentiment Detection →
Grievance Intelligence (classification?) → CRM / Ticketing Platform →
Knowledge Assistant / Agent Assist (for human agents) → Executive Dashboard (govt authority view) →
Predictive Analytics / Proactive Outreach (follow-up?)
```

Two things are worth flagging plainly:
- **This is call-centre-first**, not self-service-web-first. The breadcrumb literally reads "Call
  Centre," the KPIs tracked (AHT, FCR, CSAT, AWT-style SLA) are classic contact-centre metrics, and
  "Dialer" implies outbound calling capability Samadhan has no equivalent of. Samadhan's own
  `PROJECT.md` §4 request flow (website → API → Turn Engine → validator → jurisdiction → ticket) is a
  **materially different channel model**: no human agent in the loop by default, no phone/IVR at all.
- The AI capability names (Grievance Intelligence, Agent Assist, Predictive Analytics) strongly imply
  a **human-agent-assisted** model — AI supports call-centre agents and officials, rather than fully
  replacing the human interaction the way Samadhan's chatbot flow does for text/voice web input. This
  is Technical Inference from the naming, not a confirmed design detail.

---

## 6. AI Capabilities

The "AI & Next-Generation Capabilities" section has **7 clickable tabs**; only the first (default)
tab's content could be read before the page stopped responding to further scripted clicks (browser
automation hit a repeated "page busy" state after ~3 attempts — stopped rather than continuing to
retry per this session's own guidance against looping on a stuck interaction).

**Read in full (Verified Fact):**
- **Speech Intelligence** — "Intelligent Grievance Analysis — converts raw citizen voice interactions
  into structured, actionable insights automatically." Three sub-capabilities: Speech-to-Text (STT),
  Contextual Summarization, Intent & Sentiment Detection. Stated flow: *Voice Recording → Accurate
  Transcript → Concise Summary → Intent & Sentiment Output.*

**Names only, detail unread (Verified Fact for the name; Unknown/Unverified for what each does):**
- Grievance Intelligence
- Proactive Outreach
- Incoming Voice Agent
- Knowledge Assistant
- Agent Assist
- Predictive Analytics

No LLM, ASR, or NLU vendor/product is named anywhere (e.g. no mention of any specific speech or
language-model provider). "AI Engine" appears only as an unlabeled box in the technology-stack graphic.

---

## 7. Voice & Language Capabilities

- **Verified Fact:** Speech-to-Text is claimed as a capability (§6). The platform is call-centre/IVR
  centric, i.e. voice is the *primary*, not secondary, channel — opposite of Samadhan, where voice is
  one input mode on a website that also accepts text.
- **Verified Fact (notable non-claim):** "Multilingual Expansion" is listed under **Future Roadmap**,
  not under current capabilities or the Technology/AI sections. Read plainly, the platform is **not
  currently claiming multilingual support** — this is a specific, checkable gap in their own stated
  capability list as of this page's content, not an inference.
- **Unknown/Unverified:** which language(s) it currently operates in (presumably Hindi/English given
  the MP government context, but never stated), what ASR technology underlies "Speech-to-Text," any
  TTS/voice-output capability (never mentioned — the page describes STT and intent detection, nothing
  about the platform speaking back to a citizen).

---

## 8. Grievance Workflow

- **Verified Fact:** "Grievance Intelligence" is named as a capability, and the Executive Dashboard
  tracks "Pending Complaints," "Resolution Rate," and "SLA" — implying a ticket/complaint lifecycle
  exists with status and SLA tracking.
- **Verified Fact:** Operational KPIs named are call-centre metrics (FCR — First Call Resolution, AHT
  — Average Handling Time, CSAT, SLA, QM — Quality Monitoring), i.e. the workflow is measured the way
  a contact centre measures itself, not the way a ticketing/case-management system typically is.
- **Unknown/Unverified:** the actual field/question flow a citizen goes through, whether there's
  dynamic questioning akin to Samadhan's Turn Engine, how (or if) duplicate complaints are detected,
  how jurisdiction/department routing actually happens technically, whether photo/evidence attachment
  is supported on any channel, any escalation-path detail beyond "SLA" appearing as a tracked metric.

---

## 9. Government Integration

- **Verified Fact:** operated by MPOnline Limited (GoMP + TCS JV) — this is itself a form of deep
  government integration, since MPOnline is a government-owned entity, not a third-party vendor
  selling in from outside.
- **Verified Fact:** the page's entire pitch is aimed at **other MP government departments**
  ("Partner with the Customer Solutions Hub... your department's citizen service delivery") — i.e.
  this reads as an internal-to-government shared-services offering, not a product sold to citizens or
  to other states.
- **Unknown/Unverified:** which specific departments (if any) are currently live customers, any
  integration with CPGRAMS (India's national public grievance portal) or other state/central grievance
  systems, any data-sharing or API integration with department-specific backend systems.

---

## 10. Operational Model

- **Verified Fact (Competitor Claim on the numbers):** "Zero upfront Government investment" —
  described as a self-funding model where **citizens pay a portal fee**, and a **Common
  Service Centre (CSC) / kiosk franchise network** operates on a **40–60% revenue split**. This is a
  materially different business model from Samadhan's (which has no citizen-facing fee of any kind —
  `PROJECT.md` has no pricing model at all, being a free hackathon MVP).
- **Verified Fact:** "Statewide CSC & kiosk franchise network" is claimed as existing infrastructure —
  a huge physical distribution advantage no student hackathon team can replicate, and not something
  Samadhan should attempt to compete on directly (see §14, §16).
- **Verified Fact:** deployment flexibility is claimed — "On-Premise, Cloud, Hybrid" — consistent with
  an enterprise B2G sales pitch rather than a single fixed SaaS product.
- **Unknown/Unverified:** actual current transaction volumes, actual revenue, actual number of live
  kiosks/CSCs using this specific platform (versus MPOnline's much larger, longstanding CSC network in
  general, which predates and is broader than this specific "Customer Solutions Hub" product).

---

## 11. Samadhan vs eServices NEST (Customer Solutions Hub)

| Capability | Customer Solutions Hub (MPOnline/TCS) | Samadhan (actual, today) | Evidence | Gap/Opportunity |
|---|---|---|---|---|
| Primary channel | **Voice-first / call centre** (IVR, Dialer, live-call metrics) | **Website-first** (text + in-browser voice), no phone/IVR at all | Competitor: page content §5. Samadhan: `PROJECT.md` §2 | Genuinely different channel — see §12, §14 |
| Local languages | Claimed only as a **future roadmap item**, not a current capability | Hindi/Hinglish via ASR auto-detect + LLM prompt handling, live today | Competitor: §7 (Verified Fact of the *absence* of a current claim). Samadhan: `docs/specs/S12-voice.md` | Samadhan may already be ahead here for the specific Hindi/Hinglish case, despite far fewer resources |
| Speech-to-text | Claimed capability, vendor/architecture undisclosed | Sarvam Saarika primary, Groq Whisper fallback, ~8s timeout, no FFmpeg (`S12`) | Competitor: §6. Samadhan: repo spec | Samadhan's is fully specified and inspectable; competitor's is a black box |
| Intent detection | "Speech Intelligence" tab claims "Intent & Sentiment Detection" | Single LLM call (Groq JSON mode, Gemini Flash fallback) classifies service + extracts fields against a fixed, Pydantic-validated service spec | Competitor: §6. Samadhan: `PROJECT.md` §4 | Samadhan adds sentiment detection nowhere — plausible low-cost addition if ever useful for officer triage, not needed for MVP |
| Dynamic questioning | Not described on the page at all | Turn Engine asks only for missing required fields from the active service spec (`S05`, `S07`) | Competitor: Unknown/Unverified. Samadhan: repo spec | Can't compare — no evidence either way for competitor |
| Complaint registration | "Grievance Intelligence" + "Ticketing Platform" named, mechanism undisclosed | Ticket created only after citizen confirms a summary; `SMD-xxxx` from a DB sequence (`S10`) | Competitor: §3, §8 (names only). Samadhan: repo spec | — |
| Location/jurisdiction | Not described on the page at all | GPS (browser Geolocation) or typed place name; nearest-ward-centroid or `rapidfuzz` name match ≥ 80; district fallback (`S09`) — **GPS matching currently inert, all 5 pilot centroids are `NULL`** | Competitor: Unknown/Unverified. Samadhan: repo spec, known live gap | Samadhan's own gap (§13) is more actionable than anything competitor-derived |
| Department routing | Implied by "Grievance Intelligence" / dashboard's "Department-wise Issues," mechanism undisclosed | One service (`water_supply`) → one department (`Jal Vibhag`/BMC) in M1; new services = new YAML, no code change (`S03`) | Competitor: Unknown. Samadhan: repo spec | — |
| Duplicate detection | Not described on the page at all | **Not implemented** — only same-session/`message_id` idempotency exists, not cross-citizen duplicate detection | Competitor: Unknown. Samadhan: explicitly absent (`S02` ERRORS) | Real Samadhan gap, unrelated to competitor evidence — see §13 |
| Evidence/photo handling | Not described on the page at all | **Not implemented** — audio only, no image upload anywhere in `S01` | Competitor: Unknown. Samadhan: explicitly absent | Real Samadhan gap — see §13 |
| Authentication/citizen verification | Not described (no mention of OTP, login, or identity for citizens contacting the call centre) | **Deliberately absent** — anonymous sessions; `PROJECT.md` §2 lists OTP/phone verification under "Not now"; no phone number ever stored | Competitor: Unknown. Samadhan: explicit MVP scope decision | Neither system's citizen-facing verification is confirmed/strong; not a real gap versus this competitor specifically |
| Authority dashboard | "Executive Dashboard": Live Calls, Pending Complaints, Resolution Rate, SLA, District/Department trends, Heat Maps, Sentiment, AI Insights, Citizen Satisfaction | Streamlit dashboard: shared password, ticket list + filters, detail view, status change, reassign (`routing_corrections`), review queue, map (`S13`, `S14`, T30) | Competitor: §3 (named modules, no screenshots). Samadhan: repo spec, fully built | Competitor's claimed dashboard is broader in scope (analytics, heat maps, sentiment) — a real, named gap, see §13/§16 |
| Status tracking | "Resolution Rate," "SLA" tracked on the *authority* dashboard; no citizen-facing status-check page described | Anonymous `GET /status/{complaint_id}` — citizen self-service by complaint ID, no login (`S11`, `S15`) | Competitor: Unknown for citizen-facing status. Samadhan: repo spec, built | Samadhan may have a citizen self-service edge here — competitor's page never describes one |
| Escalation/SLA | "SLA" tracked as a dashboard metric; no escalation mechanism described | **Not implemented** — no SLA timers/auto-escalation, manual officer status changes only (`S14`) | Competitor: partial (metric only). Samadhan: explicitly absent | Real Samadhan gap — see §13, §16 |
| AI knowledge/RAG assistant | "Knowledge Assistant," "Knowledge Management System," "Agent Assist" all named — implies an internal agent-facing knowledge tool | **Not implemented** — no generative/open-ended assistant anywhere; LLM only does spec-constrained slot-filling (`PROJECT.md` §4: "must never invent") | Competitor: names only, detail unread. Samadhan: explicitly absent by design | See §14 — may be a deliberate differentiator, not just a gap |
| Analytics / district dashboards | Explicitly claimed: District-wise Trends, Department-wise Issues, Heat Maps, Sentiment Dashboard | **Not implemented** — `PROJECT.md` §2 "Not now"; no analytics tables | Competitor: §3. Samadhan: explicitly absent | Named gap, P1/P2 depending on time (§16) |
| Government/CRM integrations | "CRM Integration," "API Gateway," "Integration Layer" named | **None** for M1 | Competitor: names only. Samadhan: explicitly absent | Out of realistic reach for a hackathon team regardless |
| Multi-channel | Voice/call-centre primary, "digital, and assisted channels" claimed broadly | **Website only** — WhatsApp, calls, mobile app explicitly "Not now" | Competitor: §2, §5. Samadhan: `PROJECT.md` §2 | This is the platform's core strength and Samadhan's core scope cut — see §12, §14 |
| Business/pricing model | Citizen-paid portal fee + CSC/kiosk franchise revenue split | None — free MVP, no monetization model | Competitor: §10. Samadhan: n/a | Not an MVP-relevant comparison; noted for completeness only |

---

## 12. Overlapping Capabilities

Where the two genuinely overlap in *stated intent*, even though the channel emphasis differs:
- Both aim to turn a citizen's spoken/typed grievance into a structured, routed, trackable ticket.
- Both claim (Samadhan: verified in spec; competitor: claimed) speech-to-text plus some form of
  intent/field extraction from the raw utterance.
- Both have a government-facing dashboard concept — Samadhan's officer dashboard (built, scoped) and
  the competitor's "Executive Dashboard" (claimed, broader scope: analytics, heat maps, sentiment).
- Both are ultimately routing citizen input to the correct government department/office.

Where they clearly diverge, not overlap:
- **Channel primacy**: competitor is call-centre/voice-first with human agents in the loop
  (Agent Assist, Dialer); Samadhan is self-service web-chat-first with no human agent step before
  ticket creation.
- **Business model**: competitor has a revenue-generating franchise/fee model; Samadhan has none.
- **Scale claims**: competitor claims statewide, multi-department reach; Samadhan is an explicit
  single-service, single-city pilot by design.

---

## 13. Samadhan Gaps

Independent of the competitor comparison, these are Samadhan's own known, spec-documented gaps as of
today:

1. **Jurisdiction GPS matching is inert** — all 5 pilot ward centroids are `NULL` (`S09`), so every
   GPS-based complaint currently falls through to name-matching or district fallback. This is a data
   gap, not a code gap — the resolver logic already handles GPS correctly once centroids exist.
2. **No duplicate-complaint detection** across citizens/sessions (only same-session idempotency
   exists).
3. **No photo/evidence upload** — audio only.
4. **No SLA timers or auto-escalation** — status changes are manual only.
5. **No analytics/reporting tables or district-level views** — the one area where the competitor's
   claimed "Executive Dashboard" (§3, §11) is explicitly broader than what Samadhan has built.
6. **No citizen verification** (anonymous by design, `PROJECT.md` §2).
7. **Single service, single city** (`water_supply`, Bhopal 5 wards + 1 district office) — explicit
   pilot scope, not a technical limitation of the architecture (`S03`'s YAML-per-service design is
   built to extend without code changes).
8. **Website-only channel** — no WhatsApp, calls, IVR, or app; the competitor's core channel
   (voice/call-centre) is one Samadhan doesn't attempt at all.
9. **No TTS reply** — citizen gets text back even after a voice turn (`PROJECT.md` §2 "Not now").
10. **No rate limiting.**

None of items 1–4, 6–10 are news to the team — they're already named as "Not now" in `PROJECT.md` §2
or as open gaps in `docs/GAPS.md`. Item 5 (analytics/dashboard breadth) is the one place this
competitor research adds a genuinely new, named point of comparison worth reacting to.

---

## 14. Potential Differentiation

Given the MPOnline/TCS platform is voice/call-centre-first and enterprise-commercial, Samadhan's real
differentiation is not "we do the same thing but better" — it's a different point in the design space:

- **Self-service web-first vs. agent-assisted call-centre-first.** Samadhan removes the human agent
  from the default path entirely — the citizen's own text/voice input goes straight through an
  LLM-driven, spec-validated flow to a ticket, no call queue, no "Agent Assist" human step. This is a
  legitimate architectural difference, not just smaller-scale mimicry — cheaper to run per-complaint
  once built, no staffing/AHT/FCR overhead to manage.
- **Hard validation boundary between LLM and system state.** The Turn Engine's output is always
  Pydantic-validated against a fixed service spec; the LLM cannot invent a service, field, department,
  or office (`PROJECT.md` §4). The competitor's "Knowledge Assistant"/"Agent Assist" naming suggests a
  more open-ended, possibly generative surface for agents — which is more capable in principle but
  also a larger hallucination/attack surface. Samadhan's narrower, provably-bounded design is a fair
  thing to present to judges as a considered trade-off.
- **Zero-cost-to-citizen and zero business model**, by contrast with the competitor's citizen-paid
  portal-fee and franchise revenue-share model (§10) — worth naming explicitly if judges are familiar
  with the parent organization's existing commercial platform; a hackathon MVP framed as "free,
  transparent, no fee" is a real, simple point of contrast.
- **Zero-friction citizen status check** — Samadhan's anonymous `GET /status/{complaint_id}` (`S11`,
  `S15`) requires nothing but a complaint ID; the competitor's page never describes any citizen-facing
  self-service status mechanism at all, only officer-side "Resolution Rate"/"SLA" metrics.
- **Data minimalism.** No citizen contact details are ever stored (`PROJECT.md` §8); the status
  endpoint returns exactly four fields. Nothing on the competitor's page addresses citizen data
  handling or privacy at all — an area Samadhan can speak to concretely and they apparently cannot
  (at least not on this page).

**Strategic framing worth considering (not a technical recommendation, a pitch-narrative one):**
Because MPOnline is both the hackathon organizer and the operator of an existing statewide voice/
call-centre platform, Samadhan's pitch is probably stronger positioned as *"a complementary
self-service digital channel that reduces call-centre load and reaches citizens who prefer typing/
texting over calling"* rather than *"a replacement for what MPOnline already runs."* Directly claiming
superiority over the organizer's own platform, on metrics Samadhan cannot verify (80/20 call answer
rate, statewide kiosk reach), would be an unsupported claim exactly like the ones the research brief
told us not to make.

**Do not copy:** the call-centre/IVR/human-agent model itself — that's a completely different (and
much more expensive) system than a hackathon team can build, and isn't what Samadhan's own scope
(`PROJECT.md` §2) targets anyway.

---

## 15. Limited-Resource Implementation

| Gap (from §13) | Full-Scale Implementation | Samadhan MVP Approach | Technology | Complexity | External Dependencies | Cost | Dev Time | Production Upgrade Path |
|---|---|---|---|---|---|---|---|---|
| GPS jurisdiction inert (`NULL` centroids) | Surveyed/GIS-verified ward boundary polygons, point-in-polygon lookup | Manually look up and hardcode 5 ward centroid lat/lngs (e.g. from OpenStreetMap or Google Maps, marked `DEMO` per repo convention) into `offices.centroid_lat/lng` | None — it's a data-entry task, not a code task | Trivial | None (public map data) | Free | <1 hr | Real BMC ward boundary GeoJSON, point-in-polygon instead of nearest-centroid |
| Duplicate detection | ML-based near-duplicate/similarity detection across full complaint history | Simple rule: same `department` + same ward/office + same `issue_type` + within a time window (e.g. 24–72h) → flag as "possible duplicate" for the officer to see, not auto-merge | SQL query (`WHERE` + time window) on existing `tickets` table — no new library | Low | None | Free | 2–4 hrs | Add text-similarity (e.g. embeddings) once complaint volume justifies it |
| Photo/evidence upload | Full media pipeline: virus scan, image moderation, compression, CDN | Reuse the existing `audio` bucket pattern for a new `photos` bucket; accept one image per message, same size-cap approach as audio | Supabase Storage (already in use) | Low — mirrors existing audio upload code path | None new (same Supabase project) | Free at hackathon scale | 3–6 hrs | Add moderation/scanning before production, multi-photo support |
| SLA/escalation | Configurable SLA per service/department, automated reminders, multi-level escalation | A "days open" column computed from `created_at`, shown as a highlighted badge for tickets older than N days — no auto-action, just visibility | Pure SQL/Streamlit, no new service | Trivial | None | Free | 1–2 hrs | Real SLA engine + notification service in production |
| Analytics/district dashboards (the one area the competitor's claimed dashboard is broader) | Full BI stack, per-district drill-down, heat maps, sentiment dashboard | A single Streamlit "Overview" tab: counts by status/department/office using data already fetched for the ticket list (`S13`'s existing cached query) | pandas (already a dependency) | Low | None | Free | 2–3 hrs | Dedicated analytics tables + a real BI tool (Metabase/Superset), and eventually real heat-map/sentiment views at scale |
| Citizen verification | OTP via telecom/SMS gateway, DigiLocker/Aadhaar-linked identity | **Deliberately stay anonymous for MVP** — explicitly out of scope per `PROJECT.md` §2 | N/A for MVP | N/A | Twilio/MSG91/similar SMS gateway (only if pursued) | Real cost (SMS is per-message) | N/A for MVP | Production: OTP via SMS gateway |
| WhatsApp channel | Full WhatsApp Business API integration (Meta-approved BSP) | Not recommended pre-submission — new approval process, real cost, real lead time | Twilio/Gupshup/similar WhatsApp BSP | High | Meta Business verification (days-to-weeks), a BSP account, phone number | Real recurring cost | Days, not hours | Highest-leverage post-freeze channel expansion |
| Voice/IVR call-centre channel (the competitor's core channel) | Full contact-centre stack: Dialer, IVR, live agents, AHT/FCR/CSAT tooling | **Not recommended at any point for a 2-person hackathon team** — this is an enterprise operations build (staffing, telephony infra, contact-centre software), categorically outside "limited resources" even in production framing | N/A | Very High | Telephony/IVR vendor, staffed call centre | Substantial recurring cost | Weeks-to-months | Not a Samadhan roadmap item — a different product line entirely; note this explicitly rather than pretend it's reachable |
| TTS reply | Full expressive TTS in Hindi/Hinglish | Skip for MVP — `PROJECT.md` already marks this "Not now"; if time allows, Sarvam (already integrated for ASR) also offers TTS | Sarvam TTS API (same vendor, same key) | Low if attempted | None new | Same API budget already allocated | 2–4 hrs if attempted | N/A — already low-lift |
| Rate limiting | API gateway-level throttling | Skip for MVP — no demonstrated need at pilot scale | `slowapi` (FastAPI-compatible) | Trivial | None | Free | <1 hr if ever needed | Same approach scales to production with Redis-backed limits |

General principle: **prefer data fixes and rule-based logic over new AI/ML or new vendor
integrations** wherever the gap doesn't actually require intelligence (duplicate detection, SLA
visibility, analytics) — and **do not chase the competitor's call-centre/IVR channel at all**; it's
not a gap Samadhan should try to close, it's a different product.

---

## 16. MVP vs Production

**P0 — Must Have for MVP (before 30 Sep submission):**
- Fix the `NULL` ward centroids (data-only, near-zero cost, directly improves Scenario 7 —
  "GPS in pilot ward → correct ward office" — which today silently falls through to name-match/
  fallback even for a citizen standing in a mapped ward).
- Nothing else from this doc is P0 — `TICKETS.md` Phase 1/2 already defines the real P0 set
  (T26–T32), and this research doc should not compete with that list.

**P1 — Add if Time Permits (still within hackathon timeline):**
- Simple duplicate-complaint flag (rule-based, §15).
- "Days open" SLA visibility badge on the dashboard.
- A single-tab analytics overview (counts by status/department) — the one item this competitor
  research specifically motivates, since it's the clearest named gap versus their claimed dashboard
  breadth (§13 item 5, §11).

**P2 — Future Production Feature (explicitly not for 30 Sep, and not before the post-event freeze
lifts on 10 Oct per `PROJECT.md`):**
- Photo/evidence upload.
- WhatsApp channel.
- OTP/citizen verification.
- TTS reply.
- Real SLA/escalation engine.
- Government system integrations.
- Multi-service, multi-city expansion (architecturally ready via `S03`'s YAML spec design, just not
  built out).
- **Not on any roadmap at any tier:** a voice/IVR call-centre channel to match the competitor's core
  offering — categorically out of scope for this team and this product (§15).

**Enterprise → Hackathon substitute → Production upgrade, summarized:**

| Enterprise Implementation | Hackathon/MVP Substitute | Production Upgrade |
|---|---|---|
| GIS ward-boundary polygons + point-in-polygon | Hardcoded centroid lat/lngs, nearest-match | Real BMC ward GeoJSON |
| ML duplicate/similarity detection | SQL rule: same office+type+time window | Embedding-based similarity search |
| Full media pipeline with moderation | Direct upload to a Storage bucket, same pattern as audio | Add moderation/scanning, size/format hardening |
| SLA engine + notifications | Static "days open" badge | Configurable SLA + reminders |
| Full BI/analytics platform with heat maps & sentiment dashboards | One Streamlit summary tab over already-cached data | Dedicated analytics tables + Metabase/Superset |
| OTP via SMS gateway or Aadhaar/DigiLocker | None — stay anonymous, by design | SMS OTP gateway integration |
| WhatsApp Business API (Meta BSP) | None for 30 Sep | Twilio/Gupshup WhatsApp integration |
| Call-centre/IVR/Dialer + human agents | **None — not a Samadhan product direction** | Not applicable; a genuinely different system |

---

## 17. External Dependencies

Only for the P1 items realistically reachable before submission, since P2 items are explicitly frozen
until after 10 Oct:

| Dependency | Why Needed | Feature/Task | When Needed | Owner | Status | Blocking/Non-Blocking | Alternative |
|---|---|---|---|---|---|---|---|
| Ward centroid coordinates (5 points) | Makes GPS jurisdiction matching actually fire | Fix `offices.centroid_lat/lng` (currently `NULL`, `S09`) | Before any GPS-in-ward demo scenario is claimed working | Lead (owns `specs/`/office data per `CLAUDE.md` folder table) | Not started | **Blocking** for Scenario 7 specifically, non-blocking for everything else | Keep relying on name-match fallback (already working) if time runs out |
| None | Duplicate-flag logic is pure SQL against existing tables | Duplicate detection (§15, P1) | Whenever picked up | Dev | Not started | Non-blocking | Skip — it's a "nice to have," not required for Definition of Done |
| None | "Days open" badge computed from existing `created_at` | SLA visibility (§15, P1) | Whenever picked up | Lead/Dev (dashboard) | Not started | Non-blocking | Skip |
| None (pandas already a dependency) | Analytics tab reads already-fetched ticket data | Analytics overview (§15, P1) | Whenever picked up | Lead (dashboard owner per `CLAUDE.md`) | Not started | Non-blocking | Skip |

P2 items (WhatsApp BSP account, SMS/OTP gateway account, Sarvam TTS activation, photo-storage bucket
policy) are deliberately **not** listed here with owners/timelines — per `PROJECT.md`, nothing changes
in the product between 30 Sep submission and the event ending 10 Oct, so preparing these dependencies
"in parallel" right now would violate that freeze rather than support it.

---

## 18. Recommended Roadmap

Reasoning basis: impact (does it fix a real, demonstrable gap against Samadhan's own Definition of
Done in `PROJECT.md` §10?), feasibility (can one person do it in under a day with zero new
dependencies?), and — critically — **the 30 Sep submission freeze**, which makes "Phase 3" here mean
"after 10 Oct," not "later in the hackathon."

### Phase 1 — Hackathon MVP (now through 30 Sep)
Nothing from this research doc is required to hit Samadhan's own Definition of Done —
`TICKETS.md` already defines that critical path (T26–T32). The one item worth pulling in if there's
slack time: **fix the 5 ward centroids** (§16 P0), because it directly strengthens a scenario the
team already committed to (Scenario 7) using data that costs nothing and touches no code.

### Phase 2 — Stronger MVP (only if Phase 1 / `TICKETS.md` critical path is done early)
Rule-based duplicate flag, SLA-age badge, one-tab analytics overview (§15, all P1) — the analytics
tab is the single item this competitor research most directly motivates, since it's the clearest
named gap against the competitor's claimed dashboard breadth. Each is a few hours, no new vendor, no
new cost.

### Phase 3 — Production (after 10 Oct, once the freeze lifts)
Photo evidence, WhatsApp channel, OTP verification, TTS reply, real SLA engine, richer analytics
(district heat maps, sentiment), multi-service/multi-city expansion using the YAML-spec architecture
that already supports it. A voice/IVR call-centre channel is **not** part of this roadmap at any
phase — it's a different product line, not a Samadhan gap to close (§15).

---

## 19. Unknowns / Unverified Claims

- All performance/quality numbers on the competitor page (80% calls in 20s, 24×7 availability, "zero
  government investment," 40–60% revenue split) are **Competitor Claims** — displayed prominently, not
  independently verified.
- The 6 non-default "AI Capabilities" tabs (Grievance Intelligence, Proactive Outreach, Incoming Voice
  Agent, Knowledge Assistant, Agent Assist, Predictive Analytics) are confirmed to exist **by name**
  only — their descriptions were not retrievable before the page stopped responding to further
  scripted interaction. Re-attempting this (a human manually clicking through each tab, or a fresh
  automation session) would close this specific gap.
- No specific technology vendor (ASR provider, LLM, CRM/ticketing product, telephony/IVR platform) is
  named anywhere on the page — every capability is described only by category label.
- Whether this platform is **already live with any specific government department**, or is still in a
  pre-adoption sales/pitch phase, is not stated and not found elsewhere.
- Sub-pages linked from the top nav (Home, About, Products, Contact, "Request a Call") were not
  visited in this pass — they may contain additional detail (especially "Products," which could list
  other MPOnline digital services beyond this Call Centre platform) and are a reasonable next step if
  deeper research is wanted.
- Whether "Customer Solutions Hub" is MPOnline's only citizen-engagement product, or one of several,
  is unknown from this page alone.

---

## 20. Sources

- `https://eservicesnest.com/CustomerSolutionsHub` — read via a JavaScript-executing browser
  (`mcp__claude-in-chrome`); full page text extracted. Primary source for §1–§11, §19.
- `https://eservicesnest.com/CustomerSolutionsHub`, `https://eservicesnest.com/`,
  `https://eservicesnest.com/about`, `/robots.txt`, `/sitemap.xml` — fetched via `WebFetch`
  (non-JS-rendering); each returned only the bare page title, confirming the site is a client-rendered
  SPA. Superseded by the browser render above for actual content.
- WebSearch: `"eServicesNest" CustomerSolutionsHub`, `"eServices NEST" citizen grievance government`,
  `eservicesnest.com`, `"eServicesNest" LinkedIn`, `"eServicesNest" company India grievance software`,
  `"CustomerSolutionsHub" grievance OR complaint OR citizen`, `eServicesNest voice bot IVR municipal
  corporation` — no independent (non-eservicesnest.com) mentions found for any query.
- `docs/PROJECT.md` — confirms MPOnline Limited as the hackathon's organizing body (line 12),
  cross-referenced against the competitor page's own "MPOnline Limited... Joint Venture" statement.
- Samadhan internal sources used for the comparison side: `docs/PROJECT.md`, `docs/TICKETS.md`,
  `docs/GAPS.md`, `docs/specs/S02-db-schema.md`, `docs/specs/S09-jurisdiction.md`,
  `docs/specs/S10-ticket-routing.md`, `docs/specs/S12-voice.md`,
  `docs/specs/S13-dashboard-auth-list.md`, `docs/specs/S14-dashboard-detail-actions.md`,
  `docs/specs/S15-status-check-page.md`.

---

## FINAL TEAM-LEAD REPORT

**What they have** → A voice/call-centre-first, AI-layered citizen engagement platform ("Customer
Solutions Hub"), operated by **MPOnline Limited — the same body running this hackathon** — pitched to
other MP government departments for adoption. Claimed capabilities: Speech-to-Text + intent/sentiment
detection (confirmed in detail), five more AI capability names (Grievance Intelligence, Proactive
Outreach, Incoming Voice Agent, Knowledge Assistant, Agent Assist, Predictive Analytics — names only),
an "Executive Dashboard" with analytics/heat-maps/sentiment views, and a citizen-paid, franchise-based
revenue model with statewide CSC/kiosk reach. No specific technology vendor is disclosed anywhere.

**How they implemented/appear to implement it** → Cannot be confirmed beyond the category labels the
page itself uses (IVR Platform, Dialer, CRM Integration, AI Engine, etc.). The workflow in §5 is
Technical Inference from those names, not a verified architecture. It reads as human-agent-assisted
(Agent Assist, Dialer) rather than fully automated end-to-end like Samadhan.

**What Samadhan already has** → A specified, built voice+text chatbot flow with strict LLM-output
validation, GPS/name-based jurisdiction routing, ticket creation with confidence-based human review,
and a working dashboard (list/filter/detail/reassign/review-queue) — scoped to one service (water
supply) in one pilot city (Bhopal, 5 wards). A working anonymous citizen self-service status check,
which the competitor's page never describes having.

**What Samadhan is missing** → Duplicate detection, photo/evidence upload, SLA/escalation, richer
analytics (the one area the competitor's claimed dashboard is broader), multi-channel (especially the
voice/IVR/call-centre channel that is the competitor's actual core strength), citizen verification, TTS
replies, rate limiting — all already named as "Not now" in `PROJECT.md` or as open gaps in
`docs/GAPS.md`, so nothing here is a surprise this research uncovered except the analytics gap.

**What we can realistically implement now** → Populate the 5 ward centroids (data-only, fixes a real
GPS-routing gap today); if time allows, a rule-based duplicate flag, an SLA-age badge, and a one-tab
analytics overview — all zero-new-dependency, few-hours tasks.

**What requires external dependencies** → WhatsApp (Meta BSP approval + vendor), OTP/citizen
verification (SMS gateway), TTS (Sarvam TTS API — same vendor already in use, lowest-lift). A
voice/IVR call-centre channel would require a telephony/contact-centre stack entirely outside this
team's reach and is **not recommended as a roadmap item at all**, at any phase.

**What should be P0/P1/P2** → P0: ward centroids only. P1: duplicate flag, SLA badge, analytics tab.
P2: everything requiring a new vendor or new channel, deferred past the submission freeze per
`PROJECT.md`'s own rule that nothing changes between 30 Sep and 10 Oct.

**What we should investigate next** → (1) Decide, as a pitch-narrative question, whether to frame
Samadhan explicitly as complementary to MPOnline's own existing call-centre platform rather than
competing with it — since the hackathon organizer operates that platform, an unsupported
"we're better" claim against it is a real risk. (2) If deeper competitor detail still matters, manually
click through the 6 unread AI-capability tabs on the live page (a human, not automation, can do this
in under two minutes) and check the "Products" nav link for other MPOnline digital services that might
be more directly comparable to Samadhan's own scope.
