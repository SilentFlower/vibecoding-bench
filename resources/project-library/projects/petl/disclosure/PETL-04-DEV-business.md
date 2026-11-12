# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add crossjoin prefixes sequence for all N sources, frozen at view creation. Each str is exact prefix, None means no prefix, field names converted as existing numbered mode. Length/type mismatch, simultaneous truthy prefix and prefixes or output-header collision must raise clearly before data emission. Preserve old prefix boolean, Cartesian source/row ordering, missing short-row filling and header-only empty-source behavior. Do not silently ignore prefixes or change ordinary unprefixed duplicate-header compatibility.

Deliver real implementation, original-failing public tests at library/tests/test_development_petl_04_dev.py, and English compatibility documentation at library/docs/development-petl-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/petl/transform/joins.py
- library/tests/test_development_petl_04_dev.py
- library/docs/development-petl-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
