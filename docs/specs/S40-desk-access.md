# S40 Desk access: logins belong to an office, not to a person

Decision (the Lead, 2026-10-08): **a complaint goes to the chair (the office), not to the officer, because officers change.** Routing already works that way (S39: a ticket points at an
`offices` row, whose `officer_name` is empty and never read). This adds the other half: who may OPEN a desk's complaints, and how that changes when the officer is transferred.

## What it does
- A **login** (dashboard account) is the key to a desk. The CM office gives one, resets it, switches it off, or **hands the whole desk over** to a new person in one step. No ticket is read or changed by any of this.
- Roles that can be handed out here: `office_officer` (one desk) and `dept_head` (one department). The CM office's own accounts (`admin`, the accounts file, `cm_admin`, `evaluator`) are not managed here, and their names cannot be reused.
- **Hand over a desk:** every active office-officer login of that desk is switched off and one new login is made. The new name is checked first, so a typo changes nothing and the old holder keeps the key.
- **Temporary passwords:** a new or reset login gets a random temporary password, shown once on screen to the CM-office person, never stored (only a PBKDF2 hash is). The holder is made to choose their own at the first login
  (at least 10 characters). A "Change my password" box is in the sidebar afterwards.
- **History:** who made, reset, switched off or handed over which login, and who last used it, are recorded (`dashboard_account_events`, `last_login_at`).
- The existing login lockout (5 wrong tries lock a username for 10 minutes) applies to these logins too.

## Where
- Migration `database/migrations/008_dashboard_accounts.sql` (tables `dashboard_accounts`, `dashboard_account_events`; RLS on, grants revoked). Without it nothing breaks: the screen says to run it.
- `dashboard/src/dashboard/cm/desk_access.py` (logic), `cm/pages_access.py` (the screen, on "Accounts and Roles", CM office only), `cm/accounts.py` (`all_accounts()` merges the file accounts and the database logins), `cm_app.py` (sign-in, forced password change).
- A database login that cannot be loaded (database down, table missing) simply does not appear: the shared admin login and the accounts file still work.

## Limits
- Like all dashboard scoping, a desk login limits what the screen shows; it is not row-level security in the database (the dashboard uses the service key). Real separation needs Supabase Auth with row-level security.
- Passwords are the only factor. A real OTP or single sign-on would be better for officers; this is the first step that does not depend on a person staying in post.
- The login name is a label chosen by the CM office; nothing checks that the person is really the officer. The department should confirm each hand-over.

## Tests
`dashboard/tests/test_desk_access.py` (23: hashes only, username rules, reset, switch off, hand-over touches only its own desk, change password, scoping of a desk login, database down, no ticket is ever touched) and
`dashboard/tests/test_desk_access_screen.py` (9: the screen driven like a user, the temporary password shown once, demo mode never opens the database, the missing-table message).
