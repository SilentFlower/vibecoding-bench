# Engineering contract: TREELIB-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add treelib.navigation.resolve_path, lowest_common_ancestor and path_between. Use actual current-tree parent/successor relationships, never tag equality as identity. resolve_path consumes literal string segments (not an implicitly split string), absolute paths include root tag; explicit start provides relative paths. Zero matches is None/[], ambiguity raises by default or returns all nodes in current sibling order. Slash-containing tags and duplicate tags remain usable. path_between includes both endpoints in source-to-target order; LCA is nearest common ancestor, same-node/shared-view/missing-ID and corrupted parent chains are explicit. Iterative parent walks avoid recursion limits; this is tree navigation, not an arbitrary graph shortest-path engine.

Deliver real implementation, original-failing public tests at library/tests/test_development_treelib_06_dev.py, and English compatibility documentation at library/docs/development-treelib-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/treelib/navigation.py
- library/tests/test_development_treelib_06_dev.py
- library/docs/development-treelib-06-dev.md
