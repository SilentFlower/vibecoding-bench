# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add --params-json to real SQL2CSV. Accept a finite JSON object of scalar/null values, require exact agreement with named binds parsed by SQLAlchemy text(query), execute through connection.execute(statement,parameters) without string interpolation, eval or logging parameter values. Reject invalid JSON, nested values and missing/extra binds. Preserve the original exec_driver_sql path when absent, CSV headers/type output and query/file precedence. Ensure connection context and engine disposal execute on success, validation, query and output failures; all tests use only temporary SQLite, never network databases.

Deliver meaningful original-failing public regression tests at library/tests/test_development_csvkit_o03_dev.py and concise English compatibility documentation at library/docs/development-csvkit-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/csvkit/utilities/sql2csv.py
- library/tests/test_development_csvkit_o03_dev.py
- library/docs/development-csvkit-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
