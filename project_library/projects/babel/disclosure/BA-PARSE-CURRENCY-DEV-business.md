# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add babel.numbers.parse_currency(string, currency, locale=None, *, strict=True, numbering_system="latn") returning Decimal. Currency is mandatory and validated; support the pinned locale standard/accounting positive and negative affixes with either its actual symbol or ISO code, and its grouping/decimal/numbering symbols. Reject wrong currency, missing currency markers, trailing junk, embedded signs, unbalanced parentheses and nonfinite amounts. Strict mode requires canonical format_currency rendering at currency precision. Do not guess currencies from ambiguous symbols, silently remove interior characters or modify parse_decimal.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ba_parse_currency_dev.py and concise English compatibility documentation at library/docs/development-ba-parse-currency-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/babel/numbers.py
- library/development_tests/test_development_ba_parse_currency_dev.py
- library/docs/development-ba-parse-currency-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
