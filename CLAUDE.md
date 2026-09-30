# Samadhan

Guidance for Claude Code when working in this repository. Product source of truth: `docs/PROJECT.md`.

## Team

Two friends building a hackathon project: **Lead** and **Dev**.

## Folders

Defaults to avoid Git conflicts, not rules. Either of us can change any file; we just tell each other.

| Path | Usually | Purpose |
|------|---------|---------|
| `backend/` | Dev | Backend |
| `frontend/` | Lead | Website |
| `dashboard/` | Lead | Officer dashboard |
| `specs/` | Lead | Service YAMLs |
| `docs/` | Lead | Docs and specs (`docs/specs/`) |
| `submission/` | Lead | Submission items |
| `.claude/commands/` | Shared | Slash commands |

Docs: `docs/PROJECT.md` (source of truth), `docs/TICKETS.md` (checklist), `docs/specs/S01-api-contract.md` (API contract).

## Rules

- Never commit `.env` or API keys. Keep `.env.example` up to date.
- List every library, API and template in the README (organizer requirement).
- Tag `v1-mvp` at submission.

## Workflow

`git pull` before starting; push when something works. Unclear rule or spec? Ask each other, and update the spec if the answer matters.

## Commands

TODO: add build, run, test and lint commands. Backend: see `backend/README.md`.
