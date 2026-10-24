# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add SortedDict.irange_items/irange_values with same minimum/maximum/inclusive/reverse signature and semantics as existing irange. Return lazy iterators, yielding current values when consumed and preserving identity; ranges/order remain based on dictionary keys or configured key function, never value sort. Cover None values, empty/unbounded/exclusive/reverse/reverse-key cases. Existing irange remains key-only and structural mutation follows its existing documented iterator contract; do not promise snapshots.

Deliver real implementation, original-failing public tests at library/tests/test_development_sortedcontainers_06_dev.py, and English compatibility documentation at library/docs/development-sortedcontainers-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/sortedcontainers/sorteddict.py
- library/tests/test_development_sortedcontainers_06_dev.py
- library/docs/development-sortedcontainers-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
