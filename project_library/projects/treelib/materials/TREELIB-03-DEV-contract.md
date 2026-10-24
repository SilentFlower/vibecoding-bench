# Engineering contract: TREELIB-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add treelib.snapshot.snapshot(tree) and restore(document,tree_class=Tree,**tree_kwargs) using schema=1/root/nodes flat records with id/tag/parent/ordered children/expanded/data. Include all descendants regardless of expanded and preserve duplicate tags and sibling insertion order. Validate exact supported shape/version, unique nonempty string IDs, one coherent root, bidirectional parent/children relationships, no cycles/duplicate references/missing or unreachable nodes, and explicit empty-tree representation before returning a tree. Restore a fresh explicitly selected tree class without dynamic class execution; copy data ownership and preserve falsy data. Keep old to_json/from_json display format unchanged. Plain data must be JSON-compatible for actual JSON encoding; no arbitrary class codecs are implied.

Deliver real implementation, original-failing public tests at library/tests/test_development_treelib_03_dev.py, and English compatibility documentation at library/docs/development-treelib-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/treelib/snapshot.py
- library/tests/test_development_treelib_03_dev.py
- library/docs/development-treelib-03-dev.md
