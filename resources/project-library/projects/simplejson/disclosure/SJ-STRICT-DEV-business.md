# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement simplejson.strict.strict_loads(document,*,use_decimal=False) using the real decoder. Reject duplicate object keys at every depth after escape decoding, NaN/Infinity and finite-text numbers that overflow binary float. use_decimal=True preserves exact finite Decimal values and integer behavior. Accept normal UTF-8 bytes and text, preserve native JSON syntax errors and do not change existing loads defaults or globally toggle decoder engines.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sj_strict_dev.py and concise English compatibility documentation at library/docs/development-sj-strict-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/simplejson/strict.py
- library/development_tests/test_development_sj_strict_dev.py
- library/docs/development-sj-strict-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
