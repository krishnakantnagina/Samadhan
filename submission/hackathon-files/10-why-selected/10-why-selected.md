# Why Should Samadhan Be Selected

**Samadhan (समाधान) · MPOnline Idea & Innovation Hackathon 2026 · Problem Statement 5**

1. **It solves the real first step: getting the complaint to the right office.** The citizen speaks or types in their own words. Samadhan
   picks the department, asks only what is missing, confirms, files `SMD-xxxx` and routes it to the ward office. No department or ward
   knowledge is needed.

2. **It is built for how people in Madhya Pradesh speak.** Hindi and Hinglish, press-and-hold voice, spoken replies, and complaint numbers
   understood when said aloud.

3. **The AI is bounded, so it can be trusted in a government setting.** The model proposes; plain code checks every value against a
   service specification file. It cannot invent a department, field or office. When it is unsure, the ticket goes to the district
   office flagged `needs_review`, and every officer correction is logged.

4. **It works end to end, and we show our numbers honestly.** Routing is about 90% exact on 60 test messages; 415 backend and 35
   dashboard tests pass; five departments run on one engine; officers have a working dashboard with a review queue, reassignment and a
   map. We state the limits openly: demo office data, no GPS ward matching yet, synthetic dialect data.

5. **It scales by adding files and data, not by rewriting.** A new department is a YAML spec plus office rows. Offices and wards are
   database rows. The core is not tied to the website, so other channels can sit in front of it.

6. **It complements MPOnline's existing platform.** It is a self-service digital channel that can reduce call-centre load, not a
   replacement for the Customer Solutions Hub. We have not verified that platform's own claims and make none about it.

7. **It respects privacy by design.** Anonymous sessions, minimal stored data, a four-field status endpoint, a private audio bucket, and a
   database closed to the public key. Documents and government records are deliberately out of scope until consent-based integration.

8. **The path forward is concrete.** Verified ward data, phone-verified complaints (an SMS OTP already delivered to a real number in about
   a second), rate limiting, per-department officer accounts, then integration with MPOnline's channels, in that order.

9. **The work is transparent and reproducible.** Every module has a written spec and plan, every library and API is listed in the README,
   and the whole build is in the repository under the `v1-mvp` tag.
