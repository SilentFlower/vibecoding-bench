# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add packaging.utils.parse_legacy_sdist_filename(filename,expected_name=None). For tar.gz/zip enumerate every split whose project name validates and version parses, deduplicate semantic pairs preserving order. Without expected_name return all valid candidates as a tuple and never silently choose. With a normalized validated expected project name return only a unique matching (name,Version) pair, otherwise InvalidSdistFilename. Support legacy post releases and hyphenated names, reject unsupported extensions/no-valid-split. Existing modern parse_sdist_filename behavior remains unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_packaging_06_dev.py, and English compatibility documentation at library/docs/development-packaging-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/packaging/utils.py
- library/tests/test_development_packaging_06_dev.py
- library/docs/development-packaging-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
