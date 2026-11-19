
# quillship-cli local release board

> Maintainer-facing release board for a command-line utility and documentation bundle. This Markdown board is maintainer-facing and can lag behind JSON state.

## Current banner, copied from maintainer board

- release label: `qs-local-2026-08-rc3`
- visible lane text: `handoff almost ready`
- board checkbox copied from previous evening: `[x] validation mostly green`

## Phase tracker

| order | phase_key | board_status | owner_role | note |
|---:|---|---|---|---|
| 1 | `draft_intake` | done | release coordinator | scope file and seed manifest were readable yesterday |
| 2 | `scope_freeze` | done | release coordinator | component list was frozen after docs bundle update |
| 3 | `local_validation` | needs refresh | validation maintainer | validation review pending |
| 4 | `repair_alignment` | not started / maybe next | release coordinator | release coordinator review pending |
| 5 | `handoff_ready` | copied ready label | docs maintainer | copied from the previous evening |
| 6 | `release_wrap` | not started | maintainer | not scheduled |

## Artifact status notes

- CLI manifest and Linux packaging notes appear stable in the local records.
- The docs guide-set manifest changed at 10:18Z; a manifest scan was exported at 10:30Z.
- Packaging receipt imported at 10:37Z: passed.
- `audit/audit_history.md` contains an optimistic note about handoff prep. Recorded in the local audit history.
- A copied line in `notes/old_release_board_copy.md` says “ready to publish”. The archived board includes its scope metadata.

## Mutable status panel

The panel below is intentionally lightweight; update it after reconciling JSON state, validation categories, lookup/cache, and audit timing.

```yaml
board_panel_version: panel-rc3-2026-08-05
current_gate_label: local_validation
board_phase_wording: needs_refresh_before_next_gate
blocking_category_summary:
  - failed_or_drift_may_exist
  - stale_snapshot_may_exist
  - missing_lookup_may_exist
last_public_sync_note: "Board not yet reconciled with latest local lookup/cache evidence."
```
