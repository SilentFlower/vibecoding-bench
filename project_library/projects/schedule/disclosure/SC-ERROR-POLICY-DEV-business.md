# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement schedule.policies.with_error_policy(job, *, max_failures=3, on_error=None) for configured jobs. Preserve its bound callback arguments and return the original Job. Suppress Exception from that callback only, increment job.consecutive_failures, notify optional (original_exception,count) once, and return CancelJob when consecutive failures reach the positive integer limit; otherwise let normal Job.run reschedule once. Success resets the count and preserves return/CancelJob. Do not catch BaseException, suppress handler errors, double-wrap a job, retry immediately, or change unwrapped jobs exception behavior.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sc_error_policy_dev.py and concise English compatibility documentation at library/docs/development-sc-error-policy-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/schedule/policies.py
- library/development_tests/test_development_sc_error_policy_dev.py
- library/docs/development-sc-error-policy-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
