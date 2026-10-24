# Engineering contract: PENDULUM-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Interval.__hash__ to use the same duration representative as cross-type equality, so every Interval equal to a Duration/timedelta has its hash, including negative/zero/microsecond intervals. Preserve existing endpoint+absolute equality between Intervals; different unequal intervals may legally share a duration hash. Do not redefine endpoint identity, prohibit legal keys or change range/pickle/timezone behavior. Verify actual set/dict lookup with mixed equal types.

Deliver real implementation, original-failing public tests at library/tests/test_development_pendulum_01_dev.py, and English compatibility documentation at library/docs/development-pendulum-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pendulum/interval.py
- library/tests/test_development_pendulum_01_dev.py
- library/docs/development-pendulum-01-dev.md
