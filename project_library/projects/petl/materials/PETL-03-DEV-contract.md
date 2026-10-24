# Engineering contract: PETL-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend pivot f1 from one field to a nonempty list/tuple of fields, emitting all row dimension headers and full composite row keys. Sort by every row field then column dimension, group correctly, aggregate duplicate combinations and preserve missing cells/column ordering. Keep scalar f1 output unchanged and presorted/nonpresorted equivalence; support header-only input. Do not stringify or collapse composite identities, reuse existing aggregation and two-pass source semantics.

Deliver real implementation, original-failing public tests at library/tests/test_development_petl_03_dev.py, and English compatibility documentation at library/docs/development-petl-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/petl/transform/reshape.py
- library/tests/test_development_petl_03_dev.py
- library/docs/development-petl-03-dev.md
