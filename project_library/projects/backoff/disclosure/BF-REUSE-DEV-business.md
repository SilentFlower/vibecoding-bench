# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair reuse of the same on_exception or on_predicate decorator factory: each wrapped target must receive exactly one configured default backoff/giveup log and each user callback exactly once per event. Snapshot user handler iterables once per factory (including generators), do not mutate caller lists, and keep previously wrapped targets stable. Preserve normal success, exception identities, logger=None, custom levels and synchronous/asynchronous behavior. Do not suppress logging globally.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bf_reuse_dev.py and concise English compatibility documentation at library/docs/development-bf-reuse-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/backoff/_decorator.py
- library/tests/test_development_bf_reuse_dev.py
- library/docs/development-bf-reuse-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
