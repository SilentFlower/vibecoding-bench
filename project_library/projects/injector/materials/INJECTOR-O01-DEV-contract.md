# Engineering contract: INJECTOR-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix actual BoundKey proxy construction through Injector.create_object with explicit resolved provider kwargs. Remaining @inject constructor dependencies must still resolve; prebound providers override automatic/default values and are evaluated once. Flatten nested BoundKey declarations before evaluation with outer explicit overrides. Preserve noninject constructor and NoInject missing-argument behavior, source provider exceptions and ordinary AssistedBuilder restrictions. Prove actual constructed values/call counts rather than provider metadata alone.

Deliver meaningful original-failing public regression tests at library/tests/test_development_injector_o01_dev.py and concise English compatibility documentation at library/docs/development-injector-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/injector/__init__.py
- library/tests/test_development_injector_o01_dev.py
- library/docs/development-injector-o01-dev.md
