# Engineering contract: AT-OPTIONAL-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix attr.converters.optional for first-parameter and return annotations stored as strings, including unknown forward references. Build a valid optional annotation representation without evaluating arbitrary annotation text or changing the original converter annotations. Preserve actual-type annotations, unannotated/builtin callables, None bypass and Converter takes_self/takes_field forwarding. The wrapped converter must still execute normally for non-None values.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_at_optional_dev.py and concise English compatibility documentation at library/docs/development-at-optional-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/attr/converters.py
- library/development_tests/test_development_at_optional_dev.py
- library/docs/development-at-optional-dev.md
