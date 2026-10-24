# Engineering contract: PYRSISTENT-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair the PDeque bounded-sequence contract: normalize slices with slice.indices, match list values for empty/extreme/negative/full-length/reversed/zero-step cases, retain structural pop-based sharing for unit steps and original tuple fallback for other steps. maxlen=0 construction consumes input but stores no elements and both-end append/extend remain empty. Preserve capacity through slicing/reverse/remove/pickle-derived queues and leave the original immutable queue unchanged; retain existing negative-maxlen checks and positive truncation rules. Do not confuse pop negative-count opposite-end semantics with slice normalization.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyrsistent_03_dev.py, and English compatibility documentation at library/docs/development-pyrsistent-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyrsistent/_pdeque.py
- library/tests/test_development_pyrsistent_03_dev.py
- library/docs/development-pyrsistent-03-dev.md
