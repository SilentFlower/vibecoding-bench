# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add packaging.display.DisplayVersion as an immutable standalone display wrapper, not a change to Version internals. Construct from exact text, expose raw_version and parsed version, normalize str while display preserves exact spelling, comparison/order/hash only use Version semantics (also with plain Version). from_version represents derived/from_parts/replaced versions with raw_version=None and normalized display. Preserve pickle round trips, reject invalid versions and mutation. No raw spelling in canonical comparison keys or original Version pickle formats.

Deliver real implementation, original-failing public tests at library/tests/test_development_packaging_01_dev.py, and English compatibility documentation at library/docs/development-packaging-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/packaging/display.py
- library/tests/test_development_packaging_01_dev.py
- library/docs/development-packaging-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
