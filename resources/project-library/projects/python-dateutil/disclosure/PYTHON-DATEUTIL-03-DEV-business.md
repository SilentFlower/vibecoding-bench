# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Validate numeric timezone hour/minute components before computing offsets in ordinary dateutil.parser.parse. Reject hours outside 0..23 and minutes outside 0..59 using existing ParserError failure protocol even with ignoretz; support HH/HHMM/HH:MM both signs and preserve valid extremes/tzinfos. Do not change existing UTC/GMT reversed-sign semantics or normalize invalid minute inputs into other legal times. Valid returned datetimes must support utcoffset/isoformat.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_dateutil_03_dev.py, and English compatibility documentation at library/docs/development-python-dateutil-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/dateutil/parser/_parser.py
- library/tests/test_development_python_dateutil_03_dev.py
- library/docs/development-python-dateutil-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
