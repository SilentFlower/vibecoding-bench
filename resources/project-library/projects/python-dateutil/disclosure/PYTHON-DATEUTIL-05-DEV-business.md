# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Allow case-insensitive X- extension properties at VTIMEZONE and STANDARD/DAYLIGHT component levels in tzical, ignoring their content as nonexecuting metadata. Preserve existing transition/offset/recurrence behavior, required TZID/DTSTART/offset checks, malformed BEGIN/END and unknown NON-X standard property errors. Parameters and repeated X properties are harmless; do not fetch TZURL/X URLs, import code or relax validation for ordinary properties.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_dateutil_05_dev.py, and English compatibility documentation at library/docs/development-python-dateutil-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/dateutil/tz/tz.py
- library/tests/test_development_python_dateutil_05_dev.py
- library/docs/development-python-dateutil-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
