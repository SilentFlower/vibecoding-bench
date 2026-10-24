# Engineering contract: CH-JSON-HEADERS-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend existing JSONL adapter with duplicate_headers="last"|"error"|"suffix" via formatter kwargs. Default last preserves old output; error rejects duplicate names before consuming a row; suffix creates deterministic collision-free names _2,_3,... while reserving every original name so real columns such as a_2 are not overwritten. Materialize one-shot headers once, keep row width validation and both unicode modes, preserve input header sequence and per-call formatter defaults. Explicit policies require text names.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ch_json_headers_dev.py and concise English compatibility documentation at library/docs/development-ch-json-headers-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cli_helpers/tabular_output/json_output_adapter.py
- library/development_tests/test_development_ch_json_headers_dev.py
- library/docs/development-ch-json-headers-dev.md
