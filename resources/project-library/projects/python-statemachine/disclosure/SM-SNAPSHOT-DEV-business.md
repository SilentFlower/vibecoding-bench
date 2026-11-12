# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement statemachine.snapshots.snapshot(machine), freeze(value) and frozen StateSnapshot(states,values,allowed_events). Capture actual StateChart.configuration order, state IDs and JSON-compatible values, stable-deduplicate actual allowed_events. Deep-freeze standard containers, reject cycles/nonfinite/unsupported values. Do not run enabled_events/guards, callbacks, sends or implicit async initial activation; an unactivated configuration stays as actually observed. Clarify structural allowed events do not promise guards pass. Preserve original model/configuration/listeners.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sm_snapshot_dev.py and concise English compatibility documentation at library/docs/development-sm-snapshot-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/statemachine/snapshots.py
- library/development_tests/test_development_sm_snapshot_dev.py
- library/docs/development-sm-snapshot-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
