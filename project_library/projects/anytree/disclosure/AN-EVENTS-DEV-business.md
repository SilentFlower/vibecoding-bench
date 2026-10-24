# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add exported EventIter following AbstractIter constructor conventions. Yield (event, actual_node, depth) with event enter/leave and zero-based root depth. A complete traversal pairs visible nodes exactly once, preserves child order, uses an explicit stack, and supports deep trees without changing recursion limits. filter_ hides only that node events, stop prunes the subtree, and maxlevel=1 includes only the root (nonpositive levels yield none). Evaluate visibility once per visited node. A partially consumed iterator promises only its actual prefix, not invented closing events. Preserve existing iterators.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_an_events_dev.py and concise English compatibility documentation at library/docs/development-an-events-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/anytree/iterators/eventiter.py
- library/src/anytree/iterators/__init__.py
- library/src/anytree/__init__.py
- library/development_tests/test_development_an_events_dev.py
- library/docs/development-an-events-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
