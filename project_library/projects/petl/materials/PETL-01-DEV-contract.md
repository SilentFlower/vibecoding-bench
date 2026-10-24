# Engineering contract: PETL-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add explicit cat(..., duplicate_fields="occurrence") policy using (field name, occurrence number); default duplicate_fields="first" preserves ALL original frozen duplicate-first behavior. The opt-in policy must implement preserving every value for a single table and N-source union headers with maximum occurrence counts in stable discovery order. Explicit output header occurrence order, short rows, missing markers, empty sources and normal unique-field alignment remain correct. Build mapping once per source, do not silently select first occurrence for all duplicates or discard repeated columns.

Deliver real implementation, original-failing public tests at library/tests/test_development_petl_01_dev.py, and English compatibility documentation at library/docs/development-petl-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/petl/transform/basics.py
- library/tests/test_development_petl_01_dev.py
- library/docs/development-petl-01-dev.md
