# Engineering contract: PENDULUM-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair DateTime._subtract_timedelta for concrete Duration using its complete original _signature, matching add and corresponding subtract(**components). Preserve days/weeks/months/years and fixed hour/minute/second/microsecond distinctions across DST, negatives and month ends. Keep ordinary standard timedelta elapsed-time behavior and existing Interval subtype path. Do not equate calendar days with 24 elapsed hours or silently alter timezone/fold policies.

Deliver real implementation, original-failing public tests at library/tests/test_development_pendulum_02_dev.py, and English compatibility documentation at library/docs/development-pendulum-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pendulum/datetime.py
- library/tests/test_development_pendulum_02_dev.py
- library/docs/development-pendulum-02-dev.md
