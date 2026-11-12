# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair NullCriterion/NotNullCriterion for a ComplexCriterion operand: serialize the entire AND/OR operand bracketed before IS NULL/IS NOT NULL, using AST types rather than SQL substring searches. Preserve ordinary fields, aliases, namespace/quote context, table replacement, nested and external AND/OR grouping. Verify TRUE/FALSE/UNKNOWN rows through actual in-memory SQLite execution without negating or rewriting predicate intent.

Deliver real implementation, original-failing public tests at library/tests/test_development_pypika_06_dev.py, and English compatibility documentation at library/docs/development-pypika-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pypika/terms.py
- library/tests/test_development_pypika_06_dev.py
- library/docs/development-pypika-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
