# Engineering contract: INJECTOR-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix Binder.install(ModuleSubclass) through the owning Injector.create_object before normal module invocation, honoring existing constructor injection rather than direct module(). Preserve explicit module instances and configuration functions without reconstructing them, allow existing parent bindings and never assume bindings declared later by that same module are already available. Keep missing unannotated/uninjected parameters and original construction/configuration exceptions visible; prove actual constructor count and installed values.

Deliver meaningful original-failing public regression tests at library/tests/test_development_injector_o03_dev.py and concise English compatibility documentation at library/docs/development-injector-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/injector/__init__.py
- library/tests/test_development_injector_o03_dev.py
- library/docs/development-injector-o03-dev.md
