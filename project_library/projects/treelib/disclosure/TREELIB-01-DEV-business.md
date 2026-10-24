# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Tree.from_map as one complete import operation: validate exactly one root, all parent references and complete reachability including detached cycles/self-cycles before conversion callbacks or building nodes. Reject invalid input with useful involved IDs, never silently discard records. Accept valid out-of-order maps, preserve sibling insertion order, call id_func once per record and reject None/unhashable/colliding transformed IDs. Honor cls and explicitly forwarded **tree_kwargs, including custom node_class and constructor failures, without guessing required arguments or swallowing them. Data callbacks build a fresh tree; old legal behavior remains compatible.

Deliver real implementation, original-failing public tests at library/tests/test_development_treelib_01_dev.py, and English compatibility documentation at library/docs/development-treelib-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/treelib/tree.py
- library/tests/test_development_treelib_01_dev.py
- library/docs/development-treelib-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
