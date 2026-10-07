# S37 Scheme answers (explain a scheme from its official page)

Builds on S36 (which finds the scheme). The bot now says what the scheme IS, using only the text of that scheme's official CM Helpline page.

- **Data:** `specs/registry/scheme_details.json` (about 1.3 MB, 361 of the 362 schemes in `schemes.csv`). Built by `backend/scripts/build_scheme_details.py` from a scrape of the public detail pages
  (`KnowYourEntitleDetail.aspx?...&Schemeid=N`). The scraper is `local-research/scripts/scrape_scheme_details.py` (git-excluded; 1 request per second, raw pages cached in `local-research/data/scheme_pages/`).
  Keys kept per scheme: objective, eligibility (and exclusions), groups, kind, benefit_type, where, process, fee, amount, documents, officer, time_limit, appeal, since, payment, updated, apply_url (only https `.gov.in` / `.nic.in`).
  Not every page has every field: objective 361, eligibility 360, process 340, where 302, fee 287, amount 281, documents 137, online apply link 107. Scheme 918 has no page text.
- **Refresh:** re-run the scraper, then `build_scheme_details.py`, then `build_scheme_index.py` (the index embeds the objective too and is ignored if the details file changed).
- **Answer logic (`backend/app/scheme_answer.py`):**
  - best scheme clearly ahead (similarity >= 0.68 and 0.03 above the second): explain it. Otherwise list up to 3 names with links and ask "which one?".
  - explanation = fixed template (headings we wrote: उद्देश्य, कौन पात्र है, लाभ, आवेदन कहाँ करें, आवेदन प्रक्रिया और अपात्रता, शुल्क, दस्तावेज़; each value copied from the page and cut at a sentence end), or, with `SCHEME_EXPLAIN=1`, a Gemini plain-Hindi summary of the page.
  - the summary is shown only if it passes `grounded()`: no link, at most 900 characters, and every number in it appears in the page or in the citizen's question (Devanagari digits read as ASCII). Otherwise, and on any provider failure, the template is used.
  - always followed by the online-apply link (if the page has one), the official CM Helpline page link, and the "this may be wrong, check the official site" note.
- **Switches:** `SCHEME_LOOKUP=1` (turns on S36 + S37), `SCHEME_EXPLAIN=1` (Gemini summary), `SCHEME_RERANK=1` (S36 rerank). All off by default. Needs `GEMINI_API_KEY` for retrieval; without it the word match lists names only.
- **Limits:** the pages are what the departments wrote (some are short, outdated or inconsistent: check `updated` dates); the bot does not know whether the citizen personally qualifies; replies are long for voice (TTS reads the whole reply); a question must first be classified as information (S35 / turn engine).
- **Licence / policy:** public government pages; the scraped raw pages stay in git-excluded `local-research/`. The compact `scheme_details.json` is a shipped copy: the Lead should approve committing it (CLAUDE.md rule on scraped data), as was done for `dashboard/data/`.
