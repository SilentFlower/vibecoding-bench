# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair isoparser._calculate_weekdate to verify the calculated date actually belongs to requested ISO year/week, rejecting invalid W53 rather than rolling into next ISO year. Keep valid 53-week years and Gregorian-boundary dates, basic/extended syntax, default weekday, date bounds and existing day/week validation. Do not blanket-reject week 53 or compare Gregorian year in place of ISO year.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_dateutil_04_dev.py, and English compatibility documentation at library/docs/development-python-dateutil-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/dateutil/parser/isoparser.py
- library/tests/test_development_python_dateutil_04_dev.py
- library/docs/development-python-dateutil-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
