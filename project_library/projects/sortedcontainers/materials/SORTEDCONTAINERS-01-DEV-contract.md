# Engineering contract: SORTEDCONTAINERS-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add SortedList.add_left/add_right inherited correctly by SortedKeyList. add_left inserts before every equal comparison key (including across block boundaries); add_right preserves current add arrival order. Reuse cached-key/block/index bookkeeping, retain payload identity and key extraction semantics. Cover empty/natural/keyed/reverse-key containers, equal keys with unequal payloads, split/index invariants and subsequent bisect/deletion. Existing add remains unchanged; do not enable arbitrary unsorted insert.

Deliver real implementation, original-failing public tests at library/tests/test_development_sortedcontainers_01_dev.py, and English compatibility documentation at library/docs/development-sortedcontainers-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/sortedcontainers/sortedlist.py
- library/tests/test_development_sortedcontainers_01_dev.py
- library/docs/development-sortedcontainers-01-dev.md
