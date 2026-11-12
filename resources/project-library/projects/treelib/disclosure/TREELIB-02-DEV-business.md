# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Tree.update_node identifier updates: preflight hashability/None/collisions before mutating anything, preserve object identity and update index/root/parent successors/child predecessors consistently. Same identifier is a no-op for identity while other attributes may update. Reject renaming a node shared across multiple tree contexts rather than corrupt another view. If a property setter or relationship update fails, restore all node attribute containers, index and current-tree pointers; do not claim to reverse arbitrary external side effects or mutate/copy user data internals. Preserve existing ordinary tag/data updates and node subclass behavior. Duplicate IDs may use existing DuplicatedNodeIdError; other invalid identities fail clearly.

Deliver real implementation, original-failing public tests at library/tests/test_development_treelib_02_dev.py, and English compatibility documentation at library/docs/development-treelib-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/treelib/tree.py
- library/tests/test_development_treelib_02_dev.py
- library/docs/development-treelib-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
