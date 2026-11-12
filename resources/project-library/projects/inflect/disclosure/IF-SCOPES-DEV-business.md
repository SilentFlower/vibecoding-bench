# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement inflect.scopes.clone(engine) and temporary_options(engine,*,classical=None,count=sentinel,gender=None). Clone preserves actual engine subtype, all custom definitions and options without mutable aliasing. Temporary scope uses completed atomic classical behavior, applies actual num/gender methods, yields original engine and restores all prior state values even on failed entry or body exceptions. Nested scopes restore their immediate parent; explicit count=None clears persistent count. Rule changes inside scope are rolled back. Do not promise internal-container identity or concurrency isolation.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_if_scopes_dev.py and concise English compatibility documentation at library/docs/development-if-scopes-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/inflect/scopes.py
- library/development_tests/test_development_if_scopes_dev.py
- library/docs/development-if-scopes-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
