# Engineering contract: PYTHON-DATEUTIL-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair rrule day filtering so ordinary and ordinal weekdays in the SAME BYDAY list form a union before intersecting with BYMONTH/BYMONTHDAY/BYYEARDAY etc. Preserve pure ordinary/pure ordinal rules, negative ordinals, MONTHLY/YEARLY with BYMONTH, COUNT/UNTIL/BYSETPOS and cached/noncached results. Use actual meeting sequences across months/years, not merely an internal mask. No hardcoded dates or change to other BY attribute conjunction.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_dateutil_02_dev.py, and English compatibility documentation at library/docs/development-python-dateutil-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/dateutil/rrule.py
- library/tests/test_development_python_dateutil_02_dev.py
- library/docs/development-python-dateutil-02-dev.md
