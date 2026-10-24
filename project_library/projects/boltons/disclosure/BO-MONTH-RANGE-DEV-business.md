# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add timeutils.month_range(start,stop,step=1,*,inclusive=False,month_end="clip") for actual date objects. Use absolute month arithmetic with the original start.day as anchor; clip/skip/raise explicitly controls months lacking that day, without drifting March to a February-clipped day. Support negative month steps, leap years and exclusive/inclusive bounds, reject zero/bool/noninteger step and unknown policy. Preserve existing daterange and never model a calendar month as a fixed number of days.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_bo_month_range_dev.py and concise English compatibility documentation at library/docs/development-bo-month-range-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/boltons/timeutils.py
- library/development_tests/test_development_bo_month_range_dev.py
- library/docs/development-bo-month-range-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
