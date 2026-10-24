# Engineering contract: TREELIB-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add treelib.integrity.validate_structure(tree) returning deterministic diagnostic dictionaries code/id/related. Inspect the actual current tree.identifier scope for root validity, index-vs-node identity, missing parent/child, missing backlinks, duplicate successors, child-parent mismatch, cycles and unreachable nodes. Healthy empty/single/shared-view trees report no findings; foreign tree contexts are not corruption. Use iterative traversal to handle deep chains beyond Python recursion limits. Do not mutate, auto-repair or claim validation of arbitrary business data. Report multiple independent faults without hiding them behind the first exception and keep old traversal behavior unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_treelib_05_dev.py, and English compatibility documentation at library/docs/development-treelib-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/treelib/integrity.py
- library/tests/test_development_treelib_05_dev.py
- library/docs/development-treelib-05-dev.md
