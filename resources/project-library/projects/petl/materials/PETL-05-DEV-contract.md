# Engineering contract: PETL-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend selecteq/Table.selecteq/eq with optional key=None. Default strict equality unchanged; supplied callable normalizes both comparison target and each field, including falsey callable objects. Return original headers/rows/payloads, support complement and existing missing/error behavior, propagate callback exceptions instead of arbitrary string conversion. Target normalization once when creating view, source remains lazily iterated; no implicit lower/casefold or None conversion.

Deliver real implementation, original-failing public tests at library/tests/test_development_petl_05_dev.py, and English compatibility documentation at library/docs/development-petl-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/petl/transform/selects.py
- library/tests/test_development_petl_05_dev.py
- library/docs/development-petl-05-dev.md
