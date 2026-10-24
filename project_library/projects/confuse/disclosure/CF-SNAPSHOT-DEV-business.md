# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add ConfigView.snapshot(template=REQUIRED,*,redact=False) and confuse.snapshots.snapshot(view,...). Without template resolve nested mappings across sources and list subviews using existing view precedence; explicit templates use view.get(template). Deep-freeze dictionaries as read-only mappings and lists/tuples as tuples, retain standard immutable configuration scalar/date/Decimal/Path values, reject cycles and unsupported mutable objects. Snapshot detaches all future source changes. Redact relative marked paths including list elements and whole views as REDACTED. Do not silently serialize values or alter flatten/get.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_cf_snapshot_dev.py and concise English compatibility documentation at library/docs/development-cf-snapshot-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/confuse/snapshots.py
- library/confuse/core.py
- library/development_tests/test_development_cf_snapshot_dev.py
- library/docs/development-cf-snapshot-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
