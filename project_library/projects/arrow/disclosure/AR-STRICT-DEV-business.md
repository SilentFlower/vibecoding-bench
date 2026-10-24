# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add DateTimeParser.parse_strict(text, format_or_list, normalize_whitespace=False, *, exact_width=False) and arrow.get(text, format_or_list, strict=True, exact_width=False). Strict matching consumes the whole normalized input with valid calendar values; old parse/get extraction defaults remain unchanged. Optional exact width requires single digit M/D/H/h/m/s, three day-of-year digits and the declared fractional S count; literals are not tokens. Keep token/localization semantics including corrected numeric weekdays, format-list fallback and timezone parsing. Reject nonboolean switches, literal-only formats and exact_width without strict mode; factory strict mode requires explicit formats.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ar_strict_dev.py and concise English compatibility documentation at library/docs/development-ar-strict-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/arrow/parser.py
- library/arrow/factory.py
- library/development_tests/test_development_ar_strict_dev.py
- library/docs/development-ar-strict-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
