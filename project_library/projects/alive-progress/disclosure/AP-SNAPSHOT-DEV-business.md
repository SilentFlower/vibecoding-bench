# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add public bar_handle.snapshot() returning frozen ProgressSnapshot(count,processed,total,percent,elapsed,rate,manual,active). Read actual current counters and last sampled raw elapsed/rate values without formatting strings, flushing, updating smoothing/timers or rendering. Unknown totals use None and percent None unless manual mode; preserve skipped count vs processed distinction. Snapshots are independent immutable values, work during pause and after finish, and active reflects actual live handle state. Preserve all old handle controls, manual/unknown modes and receipts.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ap_snapshot_dev.py and concise English compatibility documentation at library/docs/development-ap-snapshot-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/alive_progress/core/progress.py
- library/alive_progress/core/snapshots.py
- library/development_tests/test_development_ap_snapshot_dev.py
- library/docs/development-ap-snapshot-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
