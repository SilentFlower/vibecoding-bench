# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add explicit Machine.explain_event for bound core FLAT nonqueued synchronous machines. This is NOT read-only: execute existing prepare_event/transition.prepare and Condition.check in actual candidate/condition order using EventData and send_event args. Report condition index/target/pass/fail/skipped/error type; failure skips remaining conditions then tries next candidate, success skips later candidates, errors stop without exception message. Never execute transition before/after/enter/exit or state change. Unknown event has no candidates/allowedFalse. No all-guards evaluation, pure-rule claim, hierarchical/async support or on_exception/finalize diagnostic callback promise.

Deliver real implementation, original-failing public tests at library/tests/test_development_transitions_06_dev.py, and English compatibility documentation at library/docs/development-transitions-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/transitions/core.py
- library/tests/test_development_transitions_06_dev.py
- library/docs/development-transitions-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
