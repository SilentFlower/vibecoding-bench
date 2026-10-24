# Engineering contract: PYRSISTENT-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair CheckedPMap.create recursive key/value construction and optional pmap_field factory to forward the already-declared ignore_extra policy. Existing correctly typed instances remain reused, default False still rejects unknown record fields, and non-extra type/invariant failures propagate. Preserve _factory_fields signature compatibility for optional factories without forcing ignore_extra onto ordinary user factories outside the checked-type protocol. Validate multiple map/record/class levels and optional None, not only a single shallow example.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyrsistent_01_dev.py, and English compatibility documentation at library/docs/development-pyrsistent-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyrsistent/_checked_types.py
- library/pyrsistent/_field_common.py
- library/tests/test_development_pyrsistent_01_dev.py
- library/docs/development-pyrsistent-01-dev.md
