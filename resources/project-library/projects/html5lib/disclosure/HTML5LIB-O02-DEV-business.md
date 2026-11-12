# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix lint.Filter(require_matching_tags=True) to assert that the open-element stack is empty only after full source exhaustion, detecting truncated final/nested StartTag streams. Unmatched EndTag must raise the documented AssertionError rather than raw IndexError. Preserve lazy yielded prefixes, source/token identity, balanced HTML/foreign namespace/void streams and explicit require_matching_tags=False fragments. Do not auto-close, consume the source twice or change serializer/tree-parser recovery semantics.

Deliver meaningful original-failing public regression tests at library/tests/test_development_html5lib_o02_dev.py and concise English compatibility documentation at library/docs/development-html5lib-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html5lib/filters/lint.py
- library/tests/test_development_html5lib_o02_dev.py
- library/docs/development-html5lib-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
