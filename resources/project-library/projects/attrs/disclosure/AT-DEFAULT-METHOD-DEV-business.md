# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Factory.from_method(method_name) as an explicit opt-in default factory. Resolve the current instance class MRO at initialization and call the winning bound instance method, allowing subclasses to override it. Validate a nonempty identifier name; reject staticmethod/classmethod/property or unbound/nonmethod values without executing them. Propagate missing methods and method exceptions. Preserve ordinary Factory callable binding, takes_self behavior, explicit supplied field values and default decorators. Do not make arbitrary generated factory closures pickleable.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_at_default_method_dev.py and concise English compatibility documentation at library/docs/development-at-default-method-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/attr/_make.py
- library/development_tests/test_development_at_default_method_dev.py
- library/docs/development-at-default-method-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
