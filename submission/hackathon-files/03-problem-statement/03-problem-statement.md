# Problem Statement and Proposed Solution

**Samadhan (समाधान) · MPOnline Idea & Innovation Hackathon 2026 · Problem Statement 5**

## 1. The problem
Citizens of Madhya Pradesh already have ways to complain: the CM Helpline, a toll-free number, email, WhatsApp and the Bhopal Municipal
Corporation (BMC) portal. What they lack is a way to **describe a problem in their own words and have it reach the right office
without knowing how the government is organised**.

### Evidence from Madhya Pradesh (Bhopal is our first example; the same pattern applies in every district)
| Finding | Source | Confidence |
|---|---|---|
| BMC is the civic body for Bhopal; head office at Harshwardhan Complex, Mata Mandir, Bhopal 462001 | [bhopal.nic.in](https://bhopal.nic.in/en/public-utility/bhopal-municipal-corporation/) | High, official |
| Civic complaints (water, road, sewerage, streetlight) can be lodged through the CM Helpline, a toll-free number, email, WhatsApp or the BMC portal, and a complaint needs a **zone or ward number** | [complainthub.org](https://complainthub.org/bmc-bhopal/) | Medium, unofficial guide |
| The structure is department → body → zone → ward. Ward count is quoted as 85 or 86 and zone count as 19 or 21 by different unofficial sources | `docs/research/T05-research.md` | Unverified, conflicting |
| Who owns a "no water" complaint is ambiguous: BMC distribution versus PHED for bulk supply | `docs/ARCHITECTURE_DEPARTMENTS.md` | Ambiguous |
| MPOnline's own Customer Solutions Hub is a voice/call-centre-first platform with an executive dashboard; multilingual support is listed only as a future item | [eservicesnest.com](https://eservicesnest.com/CustomerSolutionsHub) (competitor research, `docs/COMPETITOR_RESEARCH_ESERVICES_NEST.md`) | Their own marketing claims, not independently verified |

### What this means for the citizen
1. **Knowledge barrier.** The citizen must know the department and the ward or zone before filing.
2. **Language barrier.** Forms and menus assume standard written language; many people speak Hindi, Hinglish or a dialect.
3. **Misrouting.** Ownership is genuinely ambiguous in places, so complaints land in the wrong queue.
4. **No feedback.** Without a complaint number and a simple status check, the citizen cannot tell whether anything happened.

### What this means for officers
Raw, unstructured complaints must be read, classified and forwarded by hand before any work starts.

## 2. Proposed solution
A voice-first AI chatbot **website** that turns a spoken or typed complaint into a routed, trackable ticket:

`speak or type → understand → ask only what is missing → confirm → ticket SMD-xxxx at the right office → check status`

| Need | How Samadhan answers it |
|---|---|
| No need to know the department | Jev, our decision model, picks the department from the citizen's words; when unsure it asks "is this X or Y?" with questions we wrote |
| Own language | Hindi and Hinglish text and voice (Sarvam speech-to-text, Groq Whisper fallback) and spoken replies (Sarvam Bulbul) |
| No need to know the ward | Ward name matched fuzzily to the ward office; GPS is captured for the officer map |
| Wrong routing | Low confidence or unknown place goes to the district office as `needs_review`; officers can reassign, and every correction is logged |
| Feedback | Complaint number `SMD-xxxx`; status by typing or saying the number in the chat, or on a status page |
| Officer workload | Tickets arrive classified, with department, office, a summary and the original audio, plus a review queue and a map |

## 3. Scope of the prototype
- **Departments:** water supply (the original pilot) plus electricity, roads, sanitation and a Human Evaluation desk for unclear cases. **Office data for the
  last four is DEMO** and labelled so. Ward names are unverified.
- **Coverage:** built for all of Madhya Pradesh. The demo data covers Bhopal (5 demo wards per department plus one district fallback office each). Adding a district means adding data rows, not code.
- **Channels:** website (text, in-browser voice, GPS). WhatsApp, calls and a mobile app are out of scope for now.
- **Information questions** ("how do I get an income certificate?"): a fixed honest reply, a validated `.gov.in` link and a disclaimer.
  Samadhan does **not** answer government-information questions itself and does **not** read or verify any document.

## 4. What we deliberately did not do
- No invented answers: the AI cannot create a department, field or office.
- No document handling: documents and government records need the citizen's consent and official integration (for example DigiLocker),
  which is roadmap work.
- No claim of measured resolution-time improvement. That needs real usage over time.
