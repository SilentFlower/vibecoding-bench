# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix actual lint.Filter Doctype checks to validate publicId and systemId themselves as None or text, independently of optional name. Invalid numeric/bytes/container identifiers with a valid name must raise AssertionError; valid text identifiers with name=None must pass. Preserve token identity, lazy iteration and all existing non-Doctype validation, and verify a real parsed DOM walker stream. Do not coerce bad identifiers to text or disable lint assertions.

Deliver meaningful original-failing public regression tests at library/tests/test_development_html5lib_o01_dev.py and concise English compatibility documentation at library/docs/development-html5lib-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html5lib/filters/lint.py
- library/tests/test_development_html5lib_o01_dev.py
- library/docs/development-html5lib-o01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
