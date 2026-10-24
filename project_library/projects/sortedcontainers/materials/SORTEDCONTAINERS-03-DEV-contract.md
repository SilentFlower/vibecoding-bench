# Engineering contract: SORTEDCONTAINERS-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add sorted_copy(key=None) to SortedList/SortedKeyList, SortedSet and SortedDict. Build a fully independent container of the same logical family using the selected key, preserving members/value identities and natural ordering for None. Original content/order/strategy never change, including when new key raises. Rebind all cached bisect/irange proxies to the new index; retain empty/copy/pickle behavior. SortedList factory may return keyed/unkeyed concrete list type; no subclass constructor guarantee or implicit in-place rekey.

Deliver real implementation, original-failing public tests at library/tests/test_development_sortedcontainers_03_dev.py, and English compatibility documentation at library/docs/development-sortedcontainers-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/sortedcontainers/sortedlist.py
- library/src/sortedcontainers/sortedset.py
- library/src/sortedcontainers/sorteddict.py
- library/tests/test_development_sortedcontainers_03_dev.py
- library/docs/development-sortedcontainers-03-dev.md
