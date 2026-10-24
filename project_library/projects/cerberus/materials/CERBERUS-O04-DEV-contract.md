# Engineering contract: CERBERUS-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add actual required_if rule with schema-validated {field, equals}. Evaluate conditions at the real required-fields phase after normalization, even when the constrained field is absent; support existing sibling/dotted/root lookup, False/None conditions and defaulted discriminator fields. Reuse required/ignore_none_values/nullable semantics for presence, respect update=True and excludes handling, preserve type/ordinary dependencies behavior and report missing fields through native required errors.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cerberus_o04_dev.py and concise English compatibility documentation at library/docs/development-cerberus-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cerberus/validator.py
- library/tests/test_development_cerberus_o04_dev.py
- library/docs/development-cerberus-o04-dev.md
