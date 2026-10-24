# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add immutable formatter.SUPPORTED_OPTIONS for actual supported input keys and validate_options(options,strict=False); expose opt-in sqlparse.format(...,strict_options=True). Strict mode rejects every unknown key including None values, lists all offenders and offers deterministic nearest real-key suggestions. Require a real bool strict flag and keep existing known-value/combination validation. Default remains compatible and tolerant of extras, including current CLI filename/outfile/inplace metadata; do not accidentally enable strict over vars(args). Internal computed indent_char is not a public input option. Do not add speculative filters or silently accept a registration key that has no real implementation.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlparse_06_dev.py, and English compatibility documentation at library/docs/development-sqlparse-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlparse/formatter.py
- library/sqlparse/__init__.py
- library/tests/test_development_sqlparse_06_dev.py
- library/docs/development-sqlparse-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
