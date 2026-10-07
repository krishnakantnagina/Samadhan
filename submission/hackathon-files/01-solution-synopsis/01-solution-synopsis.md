# Samadhan (समाधान): Solution Synopsis

**MPOnline Idea & Innovation Hackathon 2026 · Problem Statement 5 · Built for all of Madhya Pradesh**  
Live: https://samadhan-web.onrender.com/ · Dashboard: https://samadhan-dashboard.onrender.com/ · Code: https://github.com/krishnakantnagina/Samadhan

> **Every voice will be heard.**

## The problem
Many people in Madhya Pradesh have a real problem but cannot write it down or explain it to the right office. A citizen is expected to know the department, the zone or ward, and how to fill a form or follow a menu. So the complaint is lost, or it reaches the wrong desk, and days go by.

Behind this sits a bigger problem: **dialect**. People speak Hindi, Hinglish and local dialects such as Bundeli and Malvi, but government systems and AI models are built for written, standard language. Services and schemes reach people only as far as the language of the system reaches them, so dialect is a quiet barrier to developing Madhya Pradesh. There is also very little real conversation data in these dialects, so AI cannot learn to understand them.

## What we built (the main problem is solved and live)
Samadhan is a **voice-first AI assistant** on the web. A citizen just speaks or types, in their own words:

1. **Sarvam speech recognition** turns the voice into text.
2. The **LLM and our engine** understand the problem, and **Jev**, our decision model, picks the right **department**.
3. It asks only for what is missing (usually the place), then asks the citizen to **confirm**.
4. The citizen gives a **mobile number**, so the officer can call back and false complaints are discouraged.
5. A ticket **`SMD-xxxx`** is created and sent to the right office, and a reply is **spoken back** with Sarvam voice. The citizen can check the status any time, by voice or text.

Officers use a **central dashboard**: tickets with department, office, summary and original audio, a review queue for unclear cases (a Human Evaluation desk), reassignment with a log, search, area analysis and a map.

## What makes it trustworthy
The AI never has the last word. Jev picks the department, the LLM extracts the details, and **plain code validates every value against a service specification file** before anything is stored. The model cannot invent a department, field or office. Information questions get a fixed, honest reply with a validated `.gov.in` link.

## The bigger goal: dialect must never be a barrier
Every conversation is stored in an organised way: the **voice, the words, the department and any officer correction**. Over time this becomes the real, labelled dialect data that Madhya Pradesh lacks. The government is the legal authority, so only the government would hold it, and only to improve public services, for example to train future language models that talk to citizens like a real person. The same engine can sit behind **WhatsApp and phone calls**, so people without a smartphone can use it too.

## Where it stands (measured, not estimated)
- Routing: about **90% exact** on 60 test messages (26 hand-written, 34 synthetic Bundeli/Malvi), measured on our earlier LLM-based routing, before Jev was added. Synthetic data was written by an LLM.
- **415 backend and 35 dashboard automated tests pass.**
- Honest limits: office data for most departments is **DEMO**; GPS does not yet pick a ward; mobile login uses a demo PIN, not a real SMS OTP; there is no rate limit yet.

## Next
Verified ward and office data, a real SMS OTP once the SMS licence is obtained, rate limiting, then WhatsApp, phone calls, more departments and districts, and clear consent rules for voice data. A citizen who is heard trusts the system, and a system that is trusted attracts business and builds the future of Madhya Pradesh.
