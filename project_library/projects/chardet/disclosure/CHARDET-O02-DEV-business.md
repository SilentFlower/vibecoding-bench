# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement chardet.details.detect_details(data, *, names="legacy") retaining actual raw encoding/confidence/language while reporting canonical Python codec and availability. Explicit names="python" may select the canonical codec only when supported; unusual UCS4 labels must retain their identity and report unsupported status instead of being relabelled UTF32. Distinguish empty/no-match, snapshot mutable bytearray input and reject invalid policies/types without changing detect defaults.

Deliver meaningful original-failing public regression tests at library/tests/test_development_chardet_o02_dev.py and concise English compatibility documentation at library/docs/development-chardet-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/chardet/details.py
- library/tests/test_development_chardet_o02_dev.py
- library/docs/development-chardet-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
