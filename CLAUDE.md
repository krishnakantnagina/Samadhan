# Samadhan

Guidance for Claude Code when working in this repository.

## Team

- **Lead:** krishnakantnagina (specs, docs, contracts)
- **Dev A:** backend
- **Dev B:** frontend and dashboard

## Repository layout

| Path | Owner | Purpose |
|------|-------|---------|
| `backend/` | Dev A | Backend |
| `frontend/` | Dev B | Frontend |
| `dashboard/` | Dev B | Dashboard |
| `specs/` | Lead | Service YAMLs |
| `docs/` | Lead | Project docs |
| `docs/contracts/` | Lead | `api.py` and `db.sql` |
| `.claude/commands/` | Shared | Slash commands |

Docs: `docs/PROJECT.md`, `docs/TICKETS.md`, `docs/GAPS.md`, `docs/CONTRACT_CHANGELOG.md`.

## Rules

- Never commit secrets. Keep `.env` local and `.env.example` up to date.

## Commands

TODO: add build, run, test and lint commands.
