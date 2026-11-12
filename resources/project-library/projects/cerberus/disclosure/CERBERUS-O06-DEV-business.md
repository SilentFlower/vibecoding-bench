# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Build cerberus.stream.iter_validated on the delivered validate_result API. Consume one record at a time with independent Validator/schema/options, yield one-based index and independent complete results, and expose continue/stop/raise policies including safe ValidationStreamError. Treat nonmapping DocumentError records as failed results, allow custom validator factories, exact max_records without lookahead, zero consumption and early close. Preserve normal custom exceptions and never materialize the entire input stream or share mutable per-record defaults.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cerberus_o06_dev.py and concise English compatibility documentation at library/docs/development-cerberus-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cerberus/stream.py
- library/tests/test_development_cerberus_o06_dev.py
- library/docs/development-cerberus-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
