# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix _Error.__init__ to materialize context exactly once and assign parent on the retained children rather than re-iterating the source. Generator/list/tuple and deliberately one-shot iterable inputs must preserve child identities and equal absolute instance/schema paths through multiple ancestors. Apply to both ValidationError and SchemaError/create_from, keep empty contexts and existing list behavior, and introduce no copied child objects or fabricated paths.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jsonschema_o03_dev.py and concise English compatibility documentation at library/docs/development-jsonschema-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/jsonschema/exceptions.py
- library/tests/test_development_jsonschema_o03_dev.py
- library/docs/development-jsonschema-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
