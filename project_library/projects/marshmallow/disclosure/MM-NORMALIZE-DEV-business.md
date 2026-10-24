# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement marshmallow.normalized.NormalizedString as a String field with keyword form="NFC" (NFC/NFD/NFKC/NFKD/None), strip=True and casefold=False, preserving standard field kwargs. Deserialize using the real String conversion, optionally strip then casefold then normalize before normal Field validators and post-load hooks. Preserve allow_none/missing/default/data_key/required behavior, original bytes validation, dump behavior and other String fields. Reject invalid policies at construction and retain independent per-schema field copies.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_mm_normalize_dev.py and concise English compatibility documentation at library/docs/development-mm-normalize-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/marshmallow/normalized.py
- library/development_tests/test_development_mm_normalize_dev.py
- library/docs/development-mm-normalize-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
