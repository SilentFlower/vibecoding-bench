# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix timeutils.dt_to_timestamp to classify awareness by tzinfo is not None and dt.utcoffset() is not None, rather than tzinfo truthiness. Falsey tzinfo with a real offset must convert correctly; tzinfo objects returning None are naive and retain the existing implied-UTC convention. Preserve negative epochs, fractional seconds, fold-specific offsets and original offset errors; do not silently use host local timezone or alter datetime objects.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_bo_timestamp_dev.py and concise English compatibility documentation at library/docs/development-bo-timestamp-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/boltons/timeutils.py
- library/development_tests/test_development_bo_timestamp_dev.py
- library/docs/development-bo-timestamp-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
