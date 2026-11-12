# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tenacity.retry.retry_if_exception_group(predicate,*,mode="all") as retry_base. On a failed outcome traverse nested BaseExceptionGroup leaves iteratively in source order, apply all/any short-circuit logic; ordinary exceptions are a single leaf. Success returns False without invoking the predicate; missing outcome raises RuntimeError. Preserve leaf identity, original exception structure, predicate exceptions and composition with retry_all/retry_any. Validate callable/mode; integrate with actual Retrying without flattening or replacing delivered groups. This feature targets the pinned Python 3.12 environment.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tn_group_dev.py and concise English compatibility documentation at library/docs/development-tn-group-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tenacity/retry.py
- library/development_tests/test_development_tn_group_dev.py
- library/docs/development-tn-group-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
