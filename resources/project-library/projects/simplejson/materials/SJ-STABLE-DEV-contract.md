# Engineering contract: SJ-STABLE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement simplejson.stable.stable_dumps(value) and stable_bytes(value): recursively require string object keys, JSON lists/scalars and finite Decimal values; reject cycles, unsupported Python containers, NaN/Infinity including Decimal variants, and lone surrogates not representable in UTF-8. Encode sorted Unicode keys, no insignificant spaces, no ASCII escaping, BOM or trailing newline. Preserve Decimal representation and standard numeric formatting; explicitly do not claim JCS normalization. Never mutate input or change legacy encoder defaults.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sj_stable_dev.py and concise English compatibility documentation at library/docs/development-sj-stable-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/simplejson/stable.py
- library/development_tests/test_development_sj_stable_dev.py
- library/docs/development-sj-stable-dev.md
