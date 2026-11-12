# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Function.get_sql/get_function_sql so caller serialization context, particularly parameter collectors, reaches each argument and nested function while preserving namespace, dialect, quote, schema and alias semantics. Normalize explicitly controlled with_alias/subquery options to prevent duplicate keyword errors. Preserve get_special_params_sql extension behavior, aggregate FILTER collection order and plain literals. Demonstrate real bound SQLite execution and ordered Qmark/Named collections; never interpolate bound user values.

Deliver real implementation, original-failing public tests at library/tests/test_development_pypika_05_dev.py, and English compatibility documentation at library/docs/development-pypika-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pypika/terms.py
- library/tests/test_development_pypika_05_dev.py
- library/docs/development-pypika-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
