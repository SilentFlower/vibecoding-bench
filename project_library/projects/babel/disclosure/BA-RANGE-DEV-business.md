# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add babel.numbers.format_number_range(start, end, *, currency=None, locale=None, collapse=True, **options). Require finite ordered Decimal-compatible endpoints. Format complete endpoints using existing format_decimal or format_currency with its options and numbering system, and join using the locale interval fallback pattern. Collapse equal rendered endpoints only when requested; do not elide currency/signs or change the old formatters. Reject reversed/nonfinite ranges and unknown currency codes.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ba_range_dev.py and concise English compatibility documentation at library/docs/development-ba-range-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/babel/numbers.py
- library/development_tests/test_development_ba_range_dev.py
- library/docs/development-ba-range-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
