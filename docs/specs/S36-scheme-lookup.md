# S36 Scheme lookup (RAG)

An information question ("ladli behna yojana kya hai", "बुजुर्गों की पेंशन") gets matching scheme names and their official CM Helpline page instead of the generic "no official information" reply.

- **Data:** `specs/registry/schemes.csv` (362 schemes, 28 departments, scraped from cmhelpline.mp.gov.in on 2026-10-01; names and links only, no eligibility or amounts). Copy of `dashboard/data/cmhelpline_schemes.csv`; refresh both together.
- **Index:** `specs/registry/schemes_index.json` (2 MB): one Gemini `gemini-embedding-001` vector (768 dims) per scheme. Build with `cd backend && uv run --env-file ../.env python scripts/build_scheme_index.py` (about a minute; the free tier answers 429 now and then, the script retries). **Rebuild whenever `schemes.csv` changes**: the index stores the CSV hash and a stale index is ignored (word match is used instead).
- **Retrieval (the R):** at question time only the question is embedded (`RETRIEVAL_QUERY`, 4 s timeout), cosine similarity against the stored vectors, plain Python, no extra library. Keep results with similarity >= 0.65 and within 0.06 of the best, at most 3. Calibrated on sample questions: right schemes score 0.66-0.76 in Hindi, Hinglish and English; off-topic questions (passport, licence, hello) score 0.55-0.63.
- **Optional rerank:** `SCHEME_RERANK=1` asks Gemini to pick, by number, which of the top 6 really answer the question (fixes cases like a war-widow scheme ranking above a marriage-aid scheme). It can only choose from the list. Off by default: on the free tier it is slow and often times out (up to 9 s); on failure the similarity order is used.
- **No generation:** the reply is fixed text plus rows of the file. Nothing a model writes reaches the citizen. Only https `*.gov.in` links are kept.
- **Fallbacks:** no key, API down or stale index -> word-overlap match on the scheme names (Hindi script only). Retrieval ran but nothing was close -> the old reply (no guessing).
- **Code:** `backend/app/schemes.py`, `info_reply.build_scheme_reply`, hook in `routes.py` after `validator.apply` (only when intent is `information`). The urgent-danger line is kept.
- **Switches:** `SCHEME_LOOKUP=1` (off by default), `SCHEME_RERANK=1` (off by default); needs `GEMINI_API_KEY`.
- **Privacy:** the question text goes to Gemini (embedding), like it already does in S35.
- **Limits:** a scheme that is not in the file cannot be found (MGNREGA, for one, is not in the CM Helpline list). The intent must first be classified as `information` by the LLM or S35; if every LLM provider is rate-limited the question is treated as out of context.
