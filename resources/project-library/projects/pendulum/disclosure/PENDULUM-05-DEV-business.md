# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend Interval.range with keyword-only closed=both/left/right/neither and limit=None/nonnegative integer, where left/right refer to traversal start/end. Preserve default inclusive two-end behavior, inverse direction, absolute and ANCHORED accumulated-step month-end restoration. Require positive index-protocol amount and valid units; reject zero/negative progress and invalid policies. Stop at finite emitted limit, same endpoint correctly, and avoid endpoint overflow. Limit counts yielded points; no sleeping or unbounded verification.

Deliver real implementation, original-failing public tests at library/tests/test_development_pendulum_05_dev.py, and English compatibility documentation at library/docs/development-pendulum-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pendulum/interval.py
- library/tests/test_development_pendulum_05_dev.py
- library/docs/development-pendulum-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
