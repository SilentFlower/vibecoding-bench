# Engineering contract: BA-DURATION-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add babel.dates.format_duration(delta, *, units=("day","hour","minute","second"), max_parts=None, length="long", locale=None). Accept nonnegative finite seconds or timedelta, decompose by explicit strictly descending unique week/day/hour/minute/second units, preserve fractional remainder in the smallest unit, omit zero components and render zero in the smallest unit. Use existing format_unit pluralization and CLDR unit list styles, falling back to standard list style for incomplete unit list patterns. max_parts truncates nonzero components without rounding. Reject calendar months/years, invalid order, negative/nonfinite values and invalid part counts; preserve format_timedelta.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ba_duration_dev.py and concise English compatibility documentation at library/docs/development-ba-duration-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/babel/dates.py
- library/development_tests/test_development_ba_duration_dev.py
- library/docs/development-ba-duration-dev.md
