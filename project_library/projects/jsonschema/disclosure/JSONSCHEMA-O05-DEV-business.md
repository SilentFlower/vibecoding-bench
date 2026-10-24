# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add validate_all(instance, *, max_errors=100) to generated validator classes and the Validator protocol, raising public exceptions.ValidationErrorGroup for nonempty actual iter_errors results and returning None when valid. Preserve original ValidationError identities/paths and normal validate/is_valid semantics. A positive nonbool integer budget bounds stored errors and consumes at most one additional error to determine truncated; group exposes truncated/limit and derive preserves them for except*. Always close the underlying generator on completion/failure/cancellation. Keyword programming/resolution/schema errors must propagate instead of being misclassified as instance errors.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jsonschema_o05_dev.py and concise English compatibility documentation at library/docs/development-jsonschema-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jsonschema/validators.py
- library/jsonschema/exceptions.py
- library/jsonschema/protocols.py
- library/tests/test_development_jsonschema_o05_dev.py
- library/docs/development-jsonschema-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
