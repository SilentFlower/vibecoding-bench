# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add humanize.calendar.calendar_interval(start,end) and frozen CalendarInterval(sign,years,months,days,seconds,microseconds) with localized text(). Require both date or both datetime endpoints, reject awareness mismatch, convert aware end into start timezone and define wall-clock Gregorian remainder. Find complete months by direct clamp-to-month-end from the earlier endpoint, never iterative month drift; derive complete years/months, retain second/microsecond remainder, normalize reverse interval magnitude with explicit sign and zero. Reuse real translation/precisedelta while keeping naturaldelta approximate duration semantics unchanged; prove leap days, Jan31, partial months, reverse and timezone endpoints.

Deliver meaningful original-failing public regression tests at library/tests/test_development_humanize_o05_dev.py and concise English compatibility documentation at library/docs/development-humanize-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/humanize/calendar.py
- library/tests/test_development_humanize_o05_dev.py
- library/docs/development-humanize-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
