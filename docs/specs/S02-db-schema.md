# S02 — DB Schema (Supabase Postgres + Storage)
Implements: T03 (`database/schema.sql`), T05, T06 · Used by: core (write/read), dashboard (read/update) · Version: v1 · Status: Draft

## PURPOSE
One schema shared by the core and the dashboard. Stores sessions, messages, tickets, offices, and routing corrections.

## SCOPE
5 tables, 2 enums, 1 sequence, 1 storage bucket. No officer/user tables in M1 (dashboard uses one shared password).

## ENUMS
- `ticket_status`: `new` · `in_progress` · `resolved` · `needs_review` (same values as S01)
- `session_status`: `active` · `completed` · `cancelled` · `expired`

## TABLES
**sessions** — one row per chat session
| Column | Type | Rule |
|---|---|---|
| id | uuid PK | = `session_id` from S01 (client-generated) |
| status | session_status | default `active` |
| service_id | text null | set once Turn Engine identifies the service |
| collected_fields | jsonb | default `{}`; only fields defined in the service spec |
| awaiting_confirmation | bool | default false |
| lat, lng | float8 null | last location sent |
| created_at, last_active_at | timestamptz | default now(); timeout uses `last_active_at` (30 min) |

**messages** — every citizen message and its stored reply
| Column | Type | Rule |
|---|---|---|
| message_id | uuid | = `message_id` from S01 (client-generated) |
| session_id | uuid FK → sessions | not null. **PK = (`session_id`, `message_id`)** → dedupe is per session, matching S01 §8 |
| input_type | text | `text`, `audio` or `location` (location-only turn, S01 D-A8); CHECK constraint |
| text | text null | citizen text |
| transcript | text null | ASR output (original, never edited) |
| audio_path | text null | Storage path |
| response | jsonb | full S01 response body (returned as-is on duplicate) |
| created_at | timestamptz | default now() |

**tickets** — one row per registered complaint
| Column | Type | Rule |
|---|---|---|
| id | bigint PK | from sequence `complaint_seq` |
| complaint_id | text unique | `SMD-` + number, zero-padded to ≥ 4 digits (never truncate above 9999) |
| session_id | uuid FK → sessions | not null |
| service_id, department | text | from service spec |
| office_id | bigint FK → offices | not null (district fallback office if no ward match) |
| status | ticket_status | default `new`; `needs_review` if confidence < 0.7 or no ward match |
| fields | jsonb | validated collected fields |
| summary_en | text | English summary for officers |
| original_text | text | citizen's original words (text or transcript) |
| audio_path | text null | original audio |
| lat, lng | float8 null | complaint location |
| routing_confidence | numeric(3,2) | 0.00–1.00 |
| created_at, updated_at | timestamptz | `updated_at` auto-updated on every change (trigger) |

**offices** — pilot jurisdiction + office directory (manual data)
| Column | Type | Rule |
|---|---|---|
| id | bigint PK | identity |
| department | text | must match a department in service specs |
| level | text | `ward` · `zone` · `municipal_corp` · `gram_panchayat` · `block` · `district` (same values as S01 `OfficeLevel`; CHECK constraint). Pilot data uses `ward` and `district` only |
| code | text | ward/district code (LGD code if known) |
| name | text | official jurisdiction (ward/district) name; used for fuzzy match, not returned as the office name |
| aliases | text[] | spellings/Hindi names for fuzzy match |
| centroid_lat, centroid_lng | float8 null | used for nearest-ward (pilot) |
| office_name | text | shown on ticket and dashboard; returned as `ticket.office.name` in S01 |
| officer_name | text null | shown on dashboard when known; `NULL` where no verified role exists (S09) — never a placeholder or invented value |
| active | bool | default true |
Unique: (`department`, `level`, `code`). Exactly one active `district` row per department.

**routing_corrections** — officer reassignments (future ML data)
| Column | Type | Rule |
|---|---|---|
| id | bigint PK | identity |
| ticket_id | bigint FK → tickets | not null |
| from_office_id, to_office_id | bigint FK → offices | not null, must differ |
| reason | text null | optional officer note |
| created_at | timestamptz | default now() |

## INDEXES
`tickets(status)`, `tickets(department)`, `tickets(created_at desc)`, `messages(session_id, created_at)`, `sessions(last_active_at)`.

## STORAGE
Bucket `audio`, **private**. Path: `{session_id}/{message_id}.{ext}`. Dashboard plays audio via short-lived signed URLs.

## RULES (security)
1. RLS **enabled on all tables with no public policies** → anon key has zero access.
2. Core and dashboard both run server-side and use the service key from env/secrets. The website never touches the DB.
3. Only the core writes `sessions`, `messages`, `tickets`. The dashboard updates only `tickets.status`, `tickets.office_id`, and inserts `routing_corrections`.
4. No citizen contact details stored in M1.
5. Seed data (T05, T20) lives in `database/seed.sql` so the DB can be rebuilt in one run.

## ERRORS / EDGE CASES
Duplicate (`session_id`, `message_id`) → PK conflict → core returns stored `response`. Missing ward → district office + `needs_review`. Reassign to same office → rejected.

## OUT OF SCOPE
Officer accounts, per-department access, citizen phone/OTP, data retention jobs, analytics tables.

## ACCEPTANCE
- [ ] `schema.sql` + `seed.sql` run cleanly on a fresh Supabase project
- [ ] Two tickets created concurrently get different `complaint_id`s; ID 10000 renders as `SMD-10000`
- [ ] Inserting the same (`session_id`, `message_id`) twice fails on PK; the same `message_id` under a different session is accepted
- [ ] Anon key cannot read any table or audio file
- [ ] Status change updates `updated_at` automatically
- [ ] Reassignment writes one `routing_corrections` row and changes `tickets.office_id`
