# Engineering contract: AR-WEEKDAY-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement the d parsing token as ISO weekday 1 through 7, converting to the same zero-based day_of_week used by ddd/dddd. Preserve existing first matching weekday in the epoch, selected year/month and complete-date precedence rules. Reject zero/eight and unsupported extra width rather than silently returning Monday. Keep named weekdays, formatting, locale behavior and all other tokens unchanged.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ar_weekday_dev.py and concise English compatibility documentation at library/docs/development-ar-weekday-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/arrow/parser.py
- library/development_tests/test_development_ar_weekday_dev.py
- library/docs/development-ar-weekday-dev.md
