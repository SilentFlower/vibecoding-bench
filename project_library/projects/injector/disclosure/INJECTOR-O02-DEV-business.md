# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix noninjectable applied to classes by validating/storing exclusions on the final __init__, preserving original class identity and both inject/noninjectable decorator orders. Handle kw-only/frozen dataclasses and merged multiple exclusions. When restricting an inherited constructor, create a subclass-local metadata wrapper instead of mutating the shared base method. Preserve function/method behavior, get_bindings exclusion, explicit additional_kwargs priority and UnknownArgument for nonexistent parameters; missing manual values must fail rather than auto-inject int zero.

Deliver meaningful original-failing public regression tests at library/tests/test_development_injector_o02_dev.py and concise English compatibility documentation at library/docs/development-injector-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/injector/__init__.py
- library/tests/test_development_injector_o02_dev.py
- library/docs/development-injector-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
