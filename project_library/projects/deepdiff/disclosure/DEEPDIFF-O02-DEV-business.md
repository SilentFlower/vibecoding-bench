# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix actual datetime_normalize temporal capability dispatch: plain date/subclasses retain date identity/value and timedelta remains a duration, neither receiving invalid hour/minute/second replace fields for any truncate setting. datetime/time continue existing truncation/timezone normalization. Do not promote date to datetime or suppress real type changes. Prove every accepted precision, nested DeepDiff, mixed date/datetime types, duration differences and DeepHash consistency, preserving all old datetime behavior.

Deliver meaningful original-failing public regression tests at library/tests/test_development_deepdiff_o02_dev.py and concise English compatibility documentation at library/docs/development-deepdiff-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/deepdiff/helper.py
- library/tests/test_development_deepdiff_o02_dev.py
- library/docs/development-deepdiff-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
