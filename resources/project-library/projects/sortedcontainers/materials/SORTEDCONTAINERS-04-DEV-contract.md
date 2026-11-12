# Engineering contract: SORTEDCONTAINERS-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add floor/ceil/lower/higher(value,default=MISSING) to list/keyed list/set/dict. Use container bisect ordering: floor last <=, ceil first >=, lower strict predecessor, higher strict successor; keyed comparisons follow sorting key, including reverse keys and duplicate-key ties. Return existing value (dict returns key/value pair) preserving identity. Missing raises KeyError unless any explicit default, including None/False, is supplied. Existing indexing/bisect behavior unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_sortedcontainers_04_dev.py, and English compatibility documentation at library/docs/development-sortedcontainers-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/sortedcontainers/sortedlist.py
- library/src/sortedcontainers/sortedset.py
- library/src/sortedcontainers/sorteddict.py
- library/src/sortedcontainers/_neighbors.py
- library/tests/test_development_sortedcontainers_04_dev.py
- library/docs/development-sortedcontainers-04-dev.md
