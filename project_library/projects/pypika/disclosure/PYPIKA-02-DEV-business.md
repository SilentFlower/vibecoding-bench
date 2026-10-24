# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair ExistsCriterion.get_sql so with_alias=True uses existing format_alias_sql on the OUTER EXISTS expression. Do not forward outer projection alias intent to the contained query. Preserve EXISTS/NOT EXISTS quoting, inner query alias isolation, existing negate behavior and unaliased WHERE semantics. Demonstrate executable SQLite projection column identity, including spaces in an alias; no external database.

Deliver real implementation, original-failing public tests at library/tests/test_development_pypika_02_dev.py, and English compatibility documentation at library/docs/development-pypika-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pypika/terms.py
- library/tests/test_development_pypika_02_dev.py
- library/docs/development-pypika-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
