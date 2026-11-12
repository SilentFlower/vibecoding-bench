# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix sized custom showindex validation to count data rows after excluding SEPARATING_LINE records, matching the actual index-consumption loop. Preserve separators at their positions, use one index per real row for list/tuple/iterator inputs, reject sized index length mismatch against real rows, and keep rendering/numeric alignment and inputs unchanged. Do not change tabulate public signature or frozen tests.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_index_dev.py and concise English compatibility documentation at library/docs/development-tb-index-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tabulate/__init__.py
- library/development_tests/test_development_tb_index_dev.py
- library/docs/development-tb-index-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
