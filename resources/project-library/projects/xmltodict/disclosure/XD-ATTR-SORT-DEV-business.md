# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add unparse(...,sort_attributes=False) with boolean validation before writing. When enabled, sort emitted attribute names lexicographically at every element after namespace rewriting, including namespace declarations; preserve child-element order, text, comments, escaping, pretty/short-empty settings and input mapping order. Default serialization must remain byte-identical. Support output streams and roundtrip parse, but do not describe this limited attribute-order option as XML canonicalization.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xd_attr_sort_dev.py and concise English compatibility documentation at library/docs/development-xd-attr-sort-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xmltodict.py
- library/development_tests/test_development_xd_attr_sort_dev.py
- library/docs/development-xd-attr-sort-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
