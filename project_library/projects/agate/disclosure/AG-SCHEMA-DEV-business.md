# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add exported Schema(columns) and SchemaValidationError. A columns mapping declares nullable/unique booleans, inclusive min/max and finite choices. Validate a real Table without mutation, returning deterministic zero-based row/column/code records in row then configured-column order; never include actual values. Nulls bypass other checks, nullable defaults True, unique ignores nulls, and duplicate reports start at the second equal value. validate(table, strict=False, max_errors=None) supports an exact positive integer error cap and strict errors with an errors tuple. Copy caller rules, reject unknown/invalid rules, reversed bounds, invalid strict/caps and missing table columns before scanning.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ag_schema_dev.py and concise English compatibility documentation at library/docs/development-ag-schema-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/agate/schema.py
- library/agate/__init__.py
- library/development_tests/test_development_ag_schema_dev.py
- library/docs/development-ag-schema-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
