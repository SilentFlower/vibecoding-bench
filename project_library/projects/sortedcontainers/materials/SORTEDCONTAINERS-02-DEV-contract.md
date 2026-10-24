# Engineering contract: SORTEDCONTAINERS-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add SortedKeyList.refresh_at(index) with Python index protocol/negative indexes. A caller explicitly changed one payload key: remove by STORED index (never search with new key), rebuild a candidate index and reinsert at current key, then atomically commit only if all comparisons/key evaluations succeed. Return original payload identity. Other payload keys are required stable; a failed refresh preserves original stored ordering/key caches, without claiming rollback of caller object changes or key callback side effects. Maintain original key-stability default contract.

Deliver real implementation, original-failing public tests at library/tests/test_development_sortedcontainers_02_dev.py, and English compatibility documentation at library/docs/development-sortedcontainers-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/sortedcontainers/sortedlist.py
- library/tests/test_development_sortedcontainers_02_dev.py
- library/docs/development-sortedcontainers-02-dev.md
