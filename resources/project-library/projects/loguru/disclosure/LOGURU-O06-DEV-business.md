# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Expose loguru.LazyValue(zero_argument_callable) and integrate event-local wrappers into actual Logger argument formatting. Mix ordinary and wrapped positional/keyword values; only actually accessed placeholders evaluate, preserving standard format specs,!s,!r,attribute/index access and color formatting. Repeated references/aliases and multiple sinks share one result per event, but later events compute anew; level/activation short-circuit stays before evaluation. Captured kwargs publish evaluated values or an explicit <unevaluated LazyValue> marker so serialize=True never forces unused computation. Keep opt(lazy=True) old all-callable semantics and propagate computation errors. Top-level argument wrappers are supported; do not silently recurse into arbitrary business containers.

Deliver meaningful original-failing public regression tests at library/tests/test_development_loguru_o06_dev.py and concise English compatibility documentation at library/docs/development-loguru-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/loguru/_logger.py
- library/loguru/__init__.py
- library/tests/test_development_loguru_o06_dev.py
- library/docs/development-loguru-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
