# Engineering contract: CATTRS-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement cattrs.strategies.decimal.configure_decimal(converter, *, allow_special=False) using paired actual structure/unstructure hooks. Decimal values travel as exact strings through existing JSON/YAML converters, preserving precision, exponent and negative-zero text without float conversion. Accept explicit strings/integers/Decimal, reject bool/float/invalid text, default reject nonfinite values with an explicit opt-in policy. Configure only the supplied converter and preserve later user-hook precedence and nested records.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cattrs_o02_dev.py and concise English compatibility documentation at library/docs/development-cattrs-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cattrs/strategies/decimal.py
- library/tests/test_development_cattrs_o02_dev.py
- library/docs/development-cattrs-o02-dev.md
