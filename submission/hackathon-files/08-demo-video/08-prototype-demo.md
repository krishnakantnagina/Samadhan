# Prototype, Demo and Proof of Concept

**Samadhan (समाधान) · MPOnline Idea & Innovation Hackathon 2026 · Problem Statement 5**

## Try it yourself (working prototype)
| | |
|---|---|
| **Live website** | [https://samadhan-web.onrender.com/](https://samadhan-web.onrender.com/) |
| **Source code** | [https://github.com/krishnakantnagina/Samadhan](https://github.com/krishnakantnagina/Samadhan) |
| **Officer dashboard** | [https://samadhan-dashboard.onrender.com](https://samadhan-dashboard.onrender.com) (tap **Demo** for sample data, no login) |

The site runs on free hosting. If it has been idle, the first message can take up to a minute while the server wakes up.

## Try it in one minute
1. Open the live website and tap **Start Conversation**. The assistant greets you in Hindi (a recorded voice) and in English.
2. Type, or press and hold the mic and say: *"No water supply in my area for 3 days"* (Hindi also works, for example *"नल में पानी नहीं आ रहा"*).
3. Samadhan asks for the missing detail, the location. Tap the location button, or type a ward or village name, for example *Misrod*.
4. It shows a summary. Reply *yes* (or *हाँ*) to confirm.
5. You get a complaint number, `SMD-xxxx`. Tap **स्थिति जानें** (check status) to look it up, typed or spoken.

Try a different department (electricity, roads, sanitation) and an information question ("how do I get an income certificate?") to see the routing and the fixed, honest reply with an official link.

## Screenshots

<table style="border:none"><tr>
<td style="border:none;width:32%"><img src="../02-presentation-pdf/img/ph-widget.jpg"><br><small><b>1.</b> Mobile: the chat opens with a Hindi and English greeting, voice, location and status buttons</small></td>
<td style="border:none;width:32%"><img src="../02-presentation-pdf/img/ph-verify.jpg"><br><small><b>2.</b> Before a complaint is filed, the citizen gives a mobile number, so the officer can call back and false complaints are discouraged</small></td>
<td style="border:none;width:32%"><img src="../02-presentation-pdf/img/ph-ticket.jpg"><br><small><b>3.</b> The complaint is registered: ticket SMD-0049, department, office and a status link</small></td>
</tr></table>

**4. The central dashboard home page** (public CM Helpline 181 totals, labelled as not Samadhan's own data)

![Dashboard home](../02-presentation-pdf/img/dash-home.jpg)

**5. Tickets and routing**, with filters and a review queue (invented demo data, clearly labelled)

![Tickets and routing](../02-presentation-pdf/img/dash-tickets.jpg)

## What works today
- Hindi and Hinglish text and voice in; spoken replies out (Sarvam speech-to-text and text-to-speech, with a Groq Whisper fallback).
- One LLM call proposes the intent, department and fields. Plain code validates every value against a service specification file, so the model cannot invent a department or office.
- Four departments on one engine (water, electricity, roads, sanitation) plus a Human Evaluation desk for unclear cases.
- Ticket `SMD-xxxx`, routed to a ward office, or to the district office marked `needs_review` when unsure.
- Officer dashboard: filters, ticket detail with the original audio, status changes, reassignment with an audit trail, review queue and map.
- Measured: about 90% exact routing on 60 test messages (synthetic dialect data); 415 backend and 35 dashboard automated tests pass.

## Honest limits
Office data for four of the five services is labelled DEMO; GPS does not yet choose a ward; mobile login uses a demo PIN, not a real SMS OTP, and there is no rate limiting yet; free-tier hosting and model limits can slow the first reply.
