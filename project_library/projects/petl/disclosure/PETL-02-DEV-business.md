# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add top-level/Table.convert_report(table,converters,errorvalue=None), eagerly consume source exactly once and return immutable replayable (table,issues) tuples. Validate converter callables and unique existing field names; retain header/order/other fields. Each failed field (including short-row access) gets replacement and ordered 1-based data row/field/error_type issue, never raw value or exception message. Report multiple errors per row, preserve successful conversions and support empty/one-shot sources. Existing lazy convert failure defaults remain unchanged; explicit snapshot memory semantics, not a streaming claim.

Deliver real implementation, original-failing public tests at library/tests/test_development_petl_02_dev.py, and English compatibility documentation at library/docs/development-petl-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/petl/transform/conversions.py
- library/petl/transform/__init__.py
- library/tests/test_development_petl_02_dev.py
- library/docs/development-petl-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
