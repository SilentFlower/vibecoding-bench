# Engineering contract: PENDULUM-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Interval.__contains__ to use unordered endpoint coverage while retaining stored start/end, invert, absolute and range direction. Include both endpoints for forward/reverse/single-point intervals, exclude outside values; preserve existing date/datetime and aware/naive comparison exceptions. No conversion between incomparable types, no silent endpoint mutation or changes to duration signs.

Deliver real implementation, original-failing public tests at library/tests/test_development_pendulum_03_dev.py, and English compatibility documentation at library/docs/development-pendulum-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pendulum/interval.py
- library/tests/test_development_pendulum_03_dev.py
- library/docs/development-pendulum-03-dev.md
