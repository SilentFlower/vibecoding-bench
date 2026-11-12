# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair default backoff/giveup logging for functools.partial and callable instances without __name__. Unwrap nested partials to a safe function name when available, otherwise use a stable type name; never call repr or expose bound arguments. Logs must not replace real return values or original exceptions with AttributeError. Preserve existing functions/methods, logger=None, levels and both predicate/exception modes without changing target call counts.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bf_callable_dev.py and concise English compatibility documentation at library/docs/development-bf-callable-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/backoff/_common.py
- library/tests/test_development_bf_callable_dev.py
- library/docs/development-bf-callable-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
