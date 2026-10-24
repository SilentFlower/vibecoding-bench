# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair dynamic retry configuration and jitter adaptation so TypeError raised inside a valid callable propagates as the same exception and is never swallowed or retried with another signature. Use binding/introspection to preserve wait-generator runtime value callbacks requiring an argument, legal dynamic max_tries/max_time and truly nullary deprecated jitter with its warning. Resolve configuration before target execution and preserve synchronous/asynchronous behavior. Do not catch all TypeError around user execution as a signature probe.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bf_typeerror_dev.py and concise English compatibility documentation at library/docs/development-bf-typeerror-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/backoff/_common.py
- library/tests/test_development_bf_typeerror_dev.py
- library/docs/development-bf-typeerror-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
