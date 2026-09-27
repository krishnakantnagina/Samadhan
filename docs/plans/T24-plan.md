# Plan: T24 — Dashboard: detail, status, reassign, review queue

Ticket: `docs/TICKETS.md` T24 (owner Lead, depends on T23 — `[x]`, done when "Saves to DB").
Spec: `docs/specs/S14-dashboard-detail-actions.md` (new).

**Scope: T24 only.** Builds on S13's list/auth/client. No map (T30 — own spec later). The only
writes this ticket makes, ever: `tickets.status`, `tickets.office_id`, `routing_corrections` inserts
(S02 RULES §3) — enforced by keeping every write in two named functions, nothing ad hoc in `app.py`.

## 1. Files to create or change

| Path | Action | Why |
|---|---|---|
| `dashboard/src/dashboard/tickets.py` | Edit | Add `get_ticket_detail`, `list_offices_for_department`, `update_status`, `reassign_ticket`, `list_routing_corrections` |
| `dashboard/src/dashboard/labels.py` | Create | The 4 field `.en` labels + enum value labels from `specs/water_supply.yaml`, hardcoded (D-S14-1) |
| `dashboard/src/dashboard/app.py` | Edit | Tabs ("All Tickets" / "Review Queue"), row selection, detail panel, status form, reassign form |
| `dashboard/tests/test_tickets.py` | Edit | Tests for all 5 new functions against fake clients |
| `docs/TICKETS.md` | Edit (last step) | Tick T24 `[x]` |

## 2. Steps, in order

**S1 — `dashboard/src/dashboard/labels.py`.**
```python
"""Citizen-facing field labels from specs/water_supply.yaml, for the detail panel (S14 D-S14-1).
No cross-project YAML loader for one hackathon ticket -- these 4 fields are stable (S03: field
names are the API contract). If specs/water_supply.yaml's labels change, update here too.
"""

FIELD_LABELS_EN = {
    "issue_type": "Issue",
    "location": "Location",
    "duration_days": "Days affected",
    "address_detail": "Address or landmark",
}

ISSUE_TYPE_LABELS_EN = {
    "no_supply": "No water supply",
    "low_pressure": "Low pressure",
    "dirty_water": "Dirty or smelly water",
    "leakage": "Pipe or tap leakage",
    "other": "Other water issue",
}


def display_field(name: str, value) -> tuple[str, str]:
    """(label, display value) for one fields[name] entry -- issue_type's value gets its own
    label lookup, everything else is shown as-is."""
    label = FIELD_LABELS_EN.get(name, name)
    if name == "issue_type":
        return label, ISSUE_TYPE_LABELS_EN.get(value, str(value))
    return label, str(value)
```

**S2 — `dashboard/src/dashboard/tickets.py` additions.**
```python
def get_ticket_detail(complaint_id: str, *, client: Client | None = None) -> dict[str, Any] | None:
    client = client or get_client()
    rows = (
        client.table("tickets")
        .select(
            "id,complaint_id,status,department,office_id,fields,summary_en,original_text,"
            "audio_path,lat,lng,routing_confidence,created_at,updated_at,"
            "offices(office_name,level)"
        )
        .eq("complaint_id", complaint_id)
        .execute()
    ).data
    return rows[0] if rows else None


def list_offices_for_department(department: str, *, client: Client | None = None) -> list[dict[str, Any]]:
    client = client or get_client()
    return (
        client.table("offices")
        .select("id,office_name,level")
        .eq("department", department)
        .eq("active", True)
        .order("level")
        .order("code")
        .execute()
    ).data


def update_status(complaint_id: str, new_status: str, *, client: Client | None = None) -> None:
    client = client or get_client()
    client.table("tickets").update({"status": new_status}).eq("complaint_id", complaint_id).execute()


class ReassignError(ValueError):
    """Reassign to the same office -- rejected in-app (S02 ERRORS), never reaches the DB."""


def reassign_ticket(
    *,
    ticket_id: int,
    from_office_id: int,
    to_office_id: int,
    reason: str | None,
    client: Client | None = None,
) -> None:
    if from_office_id == to_office_id:
        raise ReassignError("Cannot reassign a ticket to the office it's already at.")
    client = client or get_client()
    client.table("tickets").update({"office_id": to_office_id}).eq("id", ticket_id).execute()
    client.table("routing_corrections").insert(
        {
            "ticket_id": ticket_id,
            "from_office_id": from_office_id,
            "to_office_id": to_office_id,
            "reason": reason,
        }
    ).execute()


def list_routing_corrections(ticket_id: int, *, client: Client | None = None) -> list[dict[str, Any]]:
    client = client or get_client()
    return (
        client.table("routing_corrections")
        .select("from_office_id,to_office_id,reason,created_at")
        .eq("ticket_id", ticket_id)
        .order("created_at", desc=True)
        .execute()
    ).data
```

**S3 — `dashboard/tests/test_tickets.py` additions.**
Extend the existing fake-client pattern (S13's `_Query`/`FakeClient`) to also support `.update()`,
`.insert()` (already needed for `tickets`) on a second table (`offices`, `routing_corrections`), or
add a small second fake purpose-built for these five functions — whichever reads more clearly once
written; match S13's existing style, don't invent a third pattern.
- `test_get_ticket_detail_found` / `_not_found`.
- `test_list_offices_for_department_filters_active_and_department`.
- `test_update_status_writes_only_status`.
- `test_reassign_same_office_raises_before_any_call` — assert the fake's update/insert were never
  invoked (mirrors `backend/tests/test_routes.py`'s "never called" assertions).
- `test_reassign_updates_office_and_inserts_one_correction`.
- `test_list_routing_corrections_orders_newest_first`.

**S4 — `dashboard/src/dashboard/app.py` rewrite.**
Keep S13's `_require_login`, `_cached_tickets`, sidebar log-out untouched. Restructure `main()`:

```python
def _office_lookup() -> dict[int, str]:
    # All offices, all departments -- ~6 rows today, cheap to fetch once per session and reuse
    # both for the reassign dropdown and routing_corrections' from/to names (D-S14-3).
    ...  # st.session_state-cached, or its own st.cache_data(ttl=300) -- offices change rarely

def _render_detail(row: pd.Series) -> None:
    detail = get_ticket_detail(row["complaint_id"])
    if detail is None:
        st.warning("This ticket could not be loaded.")
        return

    st.subheader(detail["complaint_id"])
    for name, value in (detail["fields"] or {}).items():
        label, display = display_field(name, value)
        st.write(f"**{label}:** {display}")
    if detail["lat"] is not None:
        st.write(f"**GPS:** {detail['lat']}, {detail['lng']}")
    st.write(f"**Original message:** {detail['original_text']}")
    st.write(f"**Routing confidence:** {detail['routing_confidence']}")

    if detail["audio_path"]:
        _render_audio(detail["audio_path"])

    new_status = st.selectbox("Status", STATUSES, index=STATUSES.index(detail["status"]), key=f"status-{detail['id']}")
    if st.button("Save status", key=f"save-status-{detail['id']}"):
        update_status(detail["complaint_id"], new_status)
        st.cache_data.clear()
        st.success("Status updated.")
        st.rerun()

    offices = list_offices_for_department(detail["department"])
    options = {o["id"]: o["office_name"] for o in offices if o["id"] != detail["office_id"]}
    if options:
        to_office_id = st.selectbox("Reassign to", list(options), format_func=lambda i: options[i], key=f"office-{detail['id']}")
        reason = st.text_input("Reason (optional)", key=f"reason-{detail['id']}")
        if st.button("Reassign", key=f"reassign-{detail['id']}"):
            try:
                reassign_ticket(ticket_id=detail["id"], from_office_id=detail["office_id"], to_office_id=to_office_id, reason=reason or None)
            except ReassignError as exc:
                st.error(str(exc))
            else:
                st.cache_data.clear()
                st.success("Reassigned.")
                st.rerun()

    corrections = list_routing_corrections(detail["id"])
    if corrections:
        lookup = _office_lookup()
        st.write("**Reassignment history:**")
        for c in corrections:
            st.write(f"- {c['created_at']}: {lookup.get(c['from_office_id'], '?')} → {lookup.get(c['to_office_id'], '?')}" + (f" — {c['reason']}" if c["reason"] else ""))


def _render_audio(audio_path: str) -> None:
    try:
        signed = get_client().storage.from_("audio").create_signed_url(path=audio_path, expires_in=300)
        st.audio(signed["signedURL"])
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load audio: {exc}")


def _ticket_table(df: pd.DataFrame, *, key: str) -> None:
    event = st.dataframe(
        df[["complaint_id", "status", "department", "office_name", "summary_en", "created_at", "updated_at"]],
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key=key,
    )
    rows = event.selection.rows if event and event.selection else []
    if rows:
        _render_detail(df.iloc[rows[0]])


def main() -> None:
    _require_login()
    with st.sidebar:
        st.button("Log out", on_click=lambda: st.session_state.pop("authenticated", None))

    try:
        df = _cached_tickets()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load tickets: {exc}")
        return
    if df.empty:
        st.info("No tickets yet.")
        return

    tab_all, tab_review = st.tabs(["All Tickets", "Review Queue"])
    with tab_all:
        st.title("Tickets")
        # ... S13's existing filter widgets, unchanged, building `filtered` ...
        review_count = int((filtered["status"] == "needs_review").sum())
        if review_count:
            st.warning(f"{review_count} ticket(s) need review.")
        _ticket_table(filtered, key="all-tickets")
    with tab_review:
        st.title("Review Queue")
        queue = df[df["status"] == "needs_review"]
        if queue.empty:
            st.success("Nothing needs review.")
        else:
            _ticket_table(queue, key="review-queue")
```
`STATUSES = ["new", "in_progress", "resolved", "needs_review"]` as a module constant (mirrors
`ComplaintStatus` — dashboard has no `app.schemas` import available, same reasoning as D-S14-1).

**S5 — Run the suite.** `cd dashboard; uv run pytest`.

**S6 — Manual smoke test**, against the real seeded data (T20):
1. Log in, open "All Tickets," click a row → detail panel appears with fields/original text.
2. Change status on one ticket, confirm it persists after `st.cache_data.clear()` + rerun, and the
   list reflects it.
3. Reassign a ticket to a different same-department office; confirm `tickets.office_id` changed and
   exactly one `routing_corrections` row was written (check via `psql`, same as T06/T20's own
   verification pattern — direct DB read, not just trusting the UI).
4. Try reassigning to the *same* office already assigned → confirm it's rejected before any DB call.
5. Open "Review Queue," confirm only `needs_review` tickets show, resolve one from there (status
   change), confirm it drops out of the queue on the next interaction.

**S7 — Tick it off.** `docs/TICKETS.md`: T24 `[x]`, once S5 and S6 are both green.

## 3. Acceptance coverage

| S14 acceptance item | Satisfied by (code) | Verified by |
|---|---|---|
| "Saves to DB" | S2 `update_status`/`reassign_ticket` | S6 steps 2–3, checked directly in Postgres |
| Reassignment writes one correction + changes office | S2 `reassign_ticket` | S3 test + S6 step 3 |
| Reassign to same office rejected | S2 `ReassignError` | S3 test + S6 step 4 |
| Review queue = needs_review only, same actions | S4 `tab_review` | S6 step 5 |

## 4. New libraries
None — `st.dataframe`'s `on_select` and `.storage.from_(...).create_signed_url(...)` are already
available in the pinned `streamlit`/`supabase` versions (checked: 1.64.0 supports `on_select` since
1.35).

## 5. How this doesn't regress T23
- S13's filters, caching, and `_require_login`/log-out are untouched, only wrapped in a tab.
- `_cached_tickets()` (the S13 fetch/shape) is unchanged; `_ticket_table` reads the same `df` shape
  S13 already produced.
- No backend (`backend/`) file changes.

## Verification
1. `cd dashboard; uv sync; uv run pytest` — new + existing tests green.
2. Manual smoke test (S6) against live Supabase and the T20 seed data.
3. `cd backend; uv run pytest` — confirm still unaffected.

## Not doing in this turn
Not implementing until this plan is reviewed — same pattern as every prior ticket.
