# Engineering contract: PENDULUM-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add explicit Duration pickle reducers preserving original _signature (years/months/weeks/days and fixed components) and object state, reconstructing actual Duration/AbsoluteDuration class. Support all standard pickle protocols, shallow/deepcopy, negatives/zero/microseconds and identical anchor arithmetic; use normalized AbsoluteDuration definition when it has no signature and restore its state. Keep Interval own endpoint reducers and legacy timedelta-style loads untouched. Never load untrusted pickle or change year/month approximate totals.

Deliver real implementation, original-failing public tests at library/tests/test_development_pendulum_04_dev.py, and English compatibility documentation at library/docs/development-pendulum-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pendulum/duration.py
- library/tests/test_development_pendulum_04_dev.py
- library/docs/development-pendulum-04-dev.md
