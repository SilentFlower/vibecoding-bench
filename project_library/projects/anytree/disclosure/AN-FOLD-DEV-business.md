# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add anytree.util.fold_subtree(node, reducer) and NodeResultMap. Use iterative postorder, call reducer once per node with (actual_node, tuple_of_ordered_child_results), and return a read-only mapping keyed by node identity, including unhashable or equal-but-distinct NodeMixin subclasses. Retain references, preserve child order and original nodes, follow children only (not SymlinkNode targets), propagate reducer exceptions and reject structural cycles/repeated identities. Deep trees must not depend on Python recursion limits. Do not attach result attributes or caches to nodes.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_an_fold_dev.py and concise English compatibility documentation at library/docs/development-an-fold-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/anytree/util/fold.py
- library/src/anytree/util/__init__.py
- library/development_tests/test_development_an_fold_dev.py
- library/docs/development-an-fold-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
