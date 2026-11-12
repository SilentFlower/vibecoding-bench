# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Table.find _columns=None|string|sequence and forward through real find_one. Build an actual SQLAlchemy select of requested columns in order, preserving filters, hidden sort keys, offset/limit, streaming and configured row_type. Default full rows remain identical. Normalize through existing column naming, reject empty/duplicate/unknown projections, safely quote spaces and never interpolate SQL. No-match and nonexistent-table behavior remains empty/None without creating a table. Prove omitted fields are absent from both streamed and find_one results.

Deliver meaningful original-failing public regression tests at library/test/test_development_dataset_o02_dev.py and concise English compatibility documentation at library/docs/development-dataset-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dataset/table.py
- library/test/test_development_dataset_o02_dev.py
- library/docs/development-dataset-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
