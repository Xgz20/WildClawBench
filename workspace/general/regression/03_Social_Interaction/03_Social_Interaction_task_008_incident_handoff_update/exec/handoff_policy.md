# Incident handoff policy

Use the newest timestamped evidence. A rollback completion is a completed action, not proof of resolution. Keep INC-742 at SEV-2 with status `mitigated_monitoring` until the resolution gate passes.

The resolution gate requires both:

1. checkout error rate below 0.8% for two consecutive ten-minute windows; and
2. completed payment reconciliation.

Unconfirmed causal statements belong in `unconfirmed_hypotheses`. Do not change incident state, page responders, or publish from a draft handoff.
