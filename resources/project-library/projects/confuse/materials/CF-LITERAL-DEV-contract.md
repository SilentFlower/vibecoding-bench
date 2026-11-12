# Engineering contract: CF-LITERAL-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement confuse.literal.Literal(expected,default=REQUIRED) as a real Template. Require recursive type-and-value equality for scalars, dict keys/values and sequences: True,1,1.0 differ and list differs from tuple. Constructor detaches expected and validates explicit default against it. Conversion raises normal ConfigValueError with view path on mismatch, missing required values retain NotFoundError. Returned mutable values and defaults must be independent copies, without changing legacy Choice or coercive templates.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_cf_literal_dev.py and concise English compatibility documentation at library/docs/development-cf-literal-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/confuse/literal.py
- library/development_tests/test_development_cf_literal_dev.py
- library/docs/development-cf-literal-dev.md
