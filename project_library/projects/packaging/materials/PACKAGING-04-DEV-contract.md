# Engineering contract: PACKAGING-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add packaging.record immutable RecordEntry plus parse_record/format_record. Support exact CSV three-column path/hash/size rows, comma/Unicode/newline paths, optional empty hash/size and explicit zero sizes. Strict policy accepts canonical unpadded URLsafe-base64 SHA256/384/512 digests of correct length, rejects unsupported hashes, invalid or negative/bool sizes, wrong columns and duplicate paths. Stable LF output preserves row order and semantic roundtrip. Parsing never accesses disk, imports archive code or verifies actual installed file content; document this scope.

Deliver real implementation, original-failing public tests at library/tests/test_development_packaging_04_dev.py, and English compatibility documentation at library/docs/development-packaging-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/packaging/record.py
- library/tests/test_development_packaging_04_dev.py
- library/docs/development-packaging-04-dev.md
