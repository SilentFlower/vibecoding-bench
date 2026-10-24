# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add FieldRenamer(mapping,conflict="error"/"keep"/"overwrite") processor in structlog.processors. Freeze string mapping, reject duplicate destinations, ignore absent sources, apply all moves from original snapshot so swaps/chains work. Default external destination collision raises before any mutation; keep retains conflicting source/destination and transitively prevents moves into newly retained fields; overwrite explicitly replaces destination. Return independent outer dict preserving payload identity and untouched source; existing EventRenamer unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_structlog_03_dev.py, and English compatibility documentation at library/docs/development-structlog-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/structlog/processors.py
- library/src/structlog/_field_renamer.py
- library/tests/test_development_structlog_03_dev.py
- library/docs/development-structlog-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
