# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add explicit keyword-only default_factory=undefined to Config.get and its call shortcut. Invoke a callable factory exactly once only when neither environment nor repository contains the key, then apply the normal cast/bool rules. Empty and None source values are present, not missing. Reject simultaneous default/default_factory and noncallable factories, bound recursive lookup of the same missing key with a safe ValueError, clear the recursion guard even after errors, and preserve the identity of factory exceptions. Existing callable default values must remain ordinary values.

Deliver meaningful original-failing public regression tests at library/tests/test_development_dc_factory_dev.py and concise English compatibility documentation at library/docs/development-dc-factory-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/decouple.py
- library/tests/test_development_dc_factory_dev.py
- library/docs/development-dc-factory-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
