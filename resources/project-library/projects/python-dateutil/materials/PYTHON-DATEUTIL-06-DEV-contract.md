# Engineering contract: PYTHON-DATEUTIL-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Implement versioned pickle state for rrulebase covering rrule and rruleset with cache=True/False. Serialize only definition and cache policy, reconstruct independent locks/iterators, and restart cache computation rather than promising active iterator position. Preserve include/exclude rules/dates, timezone definitions and query results after empty/partial/full cache, deepcopy and legacy uncached dict states. Reject unknown state versions; never load untrusted external pickle. Old original tests/control files remain unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_dateutil_06_dev.py, and English compatibility documentation at library/docs/development-python-dateutil-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/dateutil/rrule.py
- library/tests/test_development_python_dateutil_06_dev.py
- library/docs/development-python-dateutil-06-dev.md
