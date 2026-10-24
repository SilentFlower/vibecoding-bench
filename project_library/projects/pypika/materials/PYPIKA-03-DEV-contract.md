# Engineering contract: PYPIKA-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Preserve QueryBuilder empty-string contract in PostgreSQLQueryBuilder: when base serialization is empty return before ON CONFLICT, conflict action or RETURNING. Cover update without assignments and insert without values/select with suffix combinations. A copied builder completed later must produce correct full SQL; repeated get_sql is pure. Preserve complete-query suffixes and existing invalid complete conflict errors. No PostgreSQL execution claim.

Deliver real implementation, original-failing public tests at library/tests/test_development_pypika_03_dev.py, and English compatibility documentation at library/docs/development-pypika-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pypika/dialects.py
- library/tests/test_development_pypika_03_dev.py
- library/docs/development-pypika-03-dev.md
