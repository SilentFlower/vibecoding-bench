# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tenacity.history.RetryHistory(max_entries=20) with wrap(fn), immutable records snapshot and clear(). Wrap actual sync/async target attempts, recording frozen AttemptRecord(sequence,elapsed,succeeded,exception_type) on each completed success or BaseException, preserving return identity and reraising the same exception. Bound storage, retain monotonic unique sequence across clear, protect concurrent snapshot and append, and preserve function metadata. Store no arguments, result values, exception objects/messages or tracebacks. Integrate by passing wrapped target into existing retry controllers; do not claim automatic per-call isolation or record an unawaited coroutine as a successful attempt.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tn_history_dev.py and concise English compatibility documentation at library/docs/development-tn-history-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tenacity/history.py
- library/development_tests/test_development_tn_history_dev.py
- library/docs/development-tn-history-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
