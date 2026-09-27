# S03 — Service Spec Format (`specs/*.yaml`)
Implements: T04 (`specs/water_supply.yaml`), T11 spec loader · Used by: Turn Engine (S05), validator, jurisdiction resolver, website (labels via API) · Version: v1 · Status: Draft

## PURPOSE
A service spec is the **only** source of services, fields, questions and the department the AI may use. The LLM never invents them; the backend validates every LLM value against the spec. A new service = a new YAML file, no code change.

## SCOPE
One file per service in `specs/`, named `<service>.yaml`. Loaded once at startup; a bad file stops startup with the file, key and reason. M1 ships one file: `water_supply.yaml`. Format version: `spec_version: 1`.

## TOP-LEVEL KEYS
| Key | Type | Required | Rule |
|---|---|---|---|
| spec_version | int | ✅ | Must be `1` |
| service | string | ✅ | `snake_case` id; must equal the filename. Stored in `sessions.service_id`, `tickets.service_id` |
| department | string | ✅ | Returned as `ticket.department` (S01). Must equal `offices.department` (S02) |
| label | `{hi, en}` | ✅ | Display name of the service |
| recognise | list[string] | ✅ | Hints for the Turn Engine to pick this service. Prompt input only, not a rule engine |
| out_of_scope | object | ✅ | `examples: list[string]`, `reply: {hi, en}`. Reply used for `action = out_of_scope` (S01 4.3) |
| pilot | object | ✅ | `city: string`, `wards: int`. Informational; the office rows are in `database/seed.sql` |
| routing | object | ✅ | See below |
| confirmation | string | ✅ | `required` (only value in v1): a ticket is created only after the citizen confirms |
| fields | list | ✅ | See below; at least one required field |

**routing**
| Key | Type | Rule |
|---|---|---|
| min_confidence | float 0–1 | Below this → fallback office + status. PROJECT.md: `0.7` |
| fallback_level | string | One of S01 `OfficeLevel` (`district`) |
| fallback_status | string | One of S02 `ticket_status` (`needs_review`) |
| max_match_distance_km | number > 0 | GPS farther than this from every ward centroid = "no ward match" → fallback |

## FIELDS
Every entry in `fields`:
| Key | Type | Required | Rule |
|---|---|---|---|
| name | string | ✅ | `snake_case`, unique in the file. It is the key in S01 `summary` and in `tickets.fields` (S02) |
| type | string | ✅ | `enum` · `location` · `integer` · `string` |
| required | bool | ✅ | `true` = the bot must collect it before `confirm` |
| label | `{hi, en}` | ✅ | Shown in the confirmation summary |
| question | `{hi, en}` | if `required` | Asked when the field is missing. Never asked for optional fields |
| hint | string | ❌ | Extraction hint for the LLM (e.g. `'3 दिन से' → 3`) |
| rule | string | ❌ | Free-text note for humans; ignored by code |

**Type-specific keys**
| Type | Extra keys | Validation |
|---|---|---|
| enum | `values`: list of `{value, hi, en}` (≥ 2, `value` unique, snake_case) | Stored value must be one of `value` |
| integer | `min`, `max` (min ≤ max) | Whole number in range |
| string | `max_length` | Length ≤ `max_length` after trimming |
| location | `ask_for` (default = `name`), `accepts.gps` (`lat`, `lng` ranges), `accepts.place_name` (`min_length`, `max_length`) | Needs GPS **or** a valid place name. `ask_for` is copied into the S01 response so the UI can show the location button |

**Where values are stored (S02)**
- `enum`, `integer`, `string` → `tickets.fields[name]` (enum stores the `value`, not the label).
- `location` → GPS in `tickets.lat/lng` (and `sessions.lat/lng`); place name in `tickets.fields[name]`.

## TURN RULES (backend enforced)
1. Ask only for a missing **required** field, one per turn, using its `question` in the citizen's language.
2. Optional fields are captured if the citizen volunteers them; never asked.
3. All required fields present → `action = confirm`, `summary` lists every captured field (S01 4.2).
4. Any LLM value that is not in the spec, fails its type rule, or names an unknown field is dropped and the field stays missing. The LLM cannot add a field, value, service or department.
5. `submit` is honoured only after the citizen confirms and all required fields validate.
6. Routing: office = `department` + jurisdiction. Confidence below `routing.min_confidence`, no ward match, or GPS beyond `max_match_distance_km` → `fallback_level` office and `fallback_status`.

## LOADER RULES (fail fast at startup)
- Valid YAML; unknown keys anywhere are rejected, and so is a key written twice in one mapping (a typo must not pass silently).
- All required keys present with the types above; `service` equals the filename.
- Field names unique; at least one `required` field; every required field has `question.hi` and `.en`; every field has `label.hi` and `.en`.
- `enum` values unique with `hi` + `en`; `integer` `min ≤ max`.
- `routing.fallback_level` ∈ S01 `OfficeLevel`; `fallback_status` ∈ S02 `ticket_status`; `min_confidence` in 0–1.
- Quote any string containing `: ` (a bare colon breaks YAML).

## ADDING A SERVICE
1. Copy `water_supply.yaml`; set `service`, `department`, `label`, `recognise`, `fields`.
2. Add `offices` rows for the new department, including one active `district` fallback (S02).
3. No API, schema or website change is needed: `summary` keys come from `fields`.
(Roadmap only: M1 ships and demos one service.)

## OUT OF SCOPE
Conditional fields, multi-language beyond `hi`/`en`, per-field regex, and a spec editor UI.

## OPEN
- **G-SPEC-1:** Dev to confirm `water_supply.yaml` (issue types, required fields, `max_match_distance_km: 5`).
- Which `out_of_scope.reply` is used when several services are loaded: `TBD` (one service in M1).

## ACCEPTANCE
- [x] `specs/water_supply.yaml` loads and passes every LOADER RULE (`backend/app/service_spec.py`, `backend/tests/spec/`)
- [x] A file with an unknown key, a duplicate field name, or a required field without a `question` stops startup with a clear message
- [ ] Scenario 1/2: "3 दिन से पानी नहीं आ रहा" → `issue_type = no_supply`, `duration_days = 3`, only `location` is asked
- [ ] Scenario 3: issue + place in one message → `confirm` with no questions
- [ ] An LLM value outside `values` (e.g. `issue_type = "electricity"`) is dropped and re-asked
- [ ] GPS beyond `max_match_distance_km` → fallback office + `needs_review`
