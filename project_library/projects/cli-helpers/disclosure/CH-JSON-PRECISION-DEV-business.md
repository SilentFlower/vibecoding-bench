# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend JSONL adapter with decimal_policy="float"|"string" and strict_json=False. Keep old defaults. String policy encodes every Decimal (including nested ones) as exact decimal text preserving scale; strict mode rejects nonfinite Decimal and float values anywhere, including string-policy Decimal NaN. Use per-call encoder settings without changing global JSON encoder state, preserve ordinary strings, large integers, unicode modes and input values, and reject invalid policy arguments before reading rows.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ch_json_precision_dev.py and concise English compatibility documentation at library/docs/development-ch-json-precision-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cli_helpers/tabular_output/json_output_adapter.py
- library/development_tests/test_development_ch_json_precision_dev.py
- library/docs/development-ch-json-precision-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
