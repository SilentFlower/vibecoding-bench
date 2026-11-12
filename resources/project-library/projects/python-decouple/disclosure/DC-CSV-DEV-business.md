# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend Csv with a keyword-only mode='legacy_shell' default and opt-in mode='csv'. The CSV mode parses one strict CSV record, preserving backslashes, # characters, empty/trailing fields, quoted delimiters and doubled double quotes; reject malformed quoting, multiple records and non-single-character CSV delimiters with ValueError. Retain existing cast/strip/post_process semantics, None and legacy shell behavior; do not change Config precedence or repository reading.

Deliver meaningful original-failing public regression tests at library/tests/test_development_dc_csv_dev.py and concise English compatibility documentation at library/docs/development-dc-csv-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/decouple.py
- library/tests/test_development_dc_csv_dev.py
- library/docs/development-dc-csv-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
