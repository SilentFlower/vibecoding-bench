# Engineering contract: LOGURU-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Logger.silence(level="INFO", *, module=None) using the existing ContextVar compatibility layer. Suppress matching records whose severity is <= threshold before message formatting, with string level or nonbool nonnegative integer; module None covers all, a string covers itself/dot-separated descendants. Scope rules to the same shared Logger core (bound loggers included), combine nested scopes additively and reset on every exit. Preserve global enable/disable and normal sink filters. Async siblings/new threads stay independent while created child tasks inherit context; do not mutate global activation to emulate local silence.

Deliver meaningful original-failing public regression tests at library/tests/test_development_loguru_o03_dev.py and concise English compatibility documentation at library/docs/development-loguru-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/loguru/_logger.py
- library/tests/test_development_loguru_o03_dev.py
- library/docs/development-loguru-o03-dev.md
