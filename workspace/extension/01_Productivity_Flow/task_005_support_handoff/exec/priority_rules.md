# Support priority and handoff rules

- Use the newest ticket row whose `updated_at` is a valid UTC timestamp.
- Exclude tickets whose newest status is `resolved` or `closed`.
- Use the newest comment with `valid: true` and a valid `created_at` timestamp.
- Never infer a missing owner. Write `UNASSIGNED` instead.
- Priority and first-response deadline are calculated from `created_at`:
  - `critical` → `P1`, due after 1 hour.
  - `high` → `P2`, due after 4 hours.
  - `medium` → `P3`, due after 12 hours.
  - `low` → `P4`, due after 24 hours.
- Preserve all deadline timestamps in UTC using `YYYY-MM-DDTHH:MM:SSZ`.
- Sort the handoff by priority number, deadline, then ticket ID.
- Do not convert a proposed next action into a customer commitment.
