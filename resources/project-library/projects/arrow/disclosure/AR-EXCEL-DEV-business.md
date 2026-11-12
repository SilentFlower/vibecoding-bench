# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Arrow.from_excel(serial, *, date_system, tzinfo=UTC) and Arrow.to_excel(*, date_system). Require string date_system 1900 or 1904 explicitly. Accept finite int/float/Decimal serials excluding booleans, preserve microsecond fractions with Decimal half-even rounding, and return Decimal serials. 1900 serial 0=1899-12-31, 59=1900-02-28, 61=1900-03-01; reject the fictitious [60,61) day and rounding into it. 1904 serial 0=1904-01-01. Negative serials map before the chosen epoch. Interpret values as wall-clock dates in the requested zone, preserve real datetime bounds and existing Unix timestamp get behavior; never guess the date system.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ar_excel_dev.py and concise English compatibility documentation at library/docs/development-ar-excel-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/arrow/arrow.py
- library/development_tests/test_development_ar_excel_dev.py
- library/docs/development-ar-excel-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
