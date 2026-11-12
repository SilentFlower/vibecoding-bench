# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair DELETE serialization to include accumulated ordered WITH definitions before DELETE as SELECT/INSERT/UPDATE do. Preserve subquery rendering, WHERE, PostgreSQL USING/RETURNING and unchanged no-CTE queries. Verify real selected-row deletion on in-memory SQLite and SQL text for PG; never connect external databases or claim server-specific engine/lock integration.

Deliver real implementation, original-failing public tests at library/tests/test_development_pypika_04_dev.py, and English compatibility documentation at library/docs/development-pypika-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pypika/queries.py
- library/tests/test_development_pypika_04_dev.py
- library/docs/development-pypika-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
