# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Resolver.get_by_segments(node, segments, *, absolute=False). Segments are a finite iterable of strings, never a single string/bytes. Treat slash, empty strings, dots, dot-dot and wildcard text as literal child attribute values, preserving pathattr, ignorecase, relax and existing first-match rules. Relative empty segments return the start node. Absolute mode starts at node.root and requires an explicit root-name first segment. Preserve get/glob and their navigation rules.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_an_segments_dev.py and concise English compatibility documentation at library/docs/development-an-segments-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/anytree/resolver.py
- library/development_tests/test_development_an_segments_dev.py
- library/docs/development-an-segments-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
