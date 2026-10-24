# Engineering contract: PYTHON-DATEUTIL-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair RFC unfolding in rrulestr(unfold=True)/compatible and tzical so both SP and HTAB continuation prefixes join the preceding content line, removing exactly one prefix character. Preserve existing default non-unfold rules, blank-line policy and value whitespace; do not strip all content. Verify actual recurrence instances and offset of a folded VTIMEZONE. No external calendars, network or zone service.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_dateutil_01_dev.py, and English compatibility documentation at library/docs/development-python-dateutil-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/dateutil/rrule.py
- library/src/dateutil/tz/tz.py
- library/tests/test_development_python_dateutil_01_dev.py
- library/docs/development-python-dateutil-01-dev.md
