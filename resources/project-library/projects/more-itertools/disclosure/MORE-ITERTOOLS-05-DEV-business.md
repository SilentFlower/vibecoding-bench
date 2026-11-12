# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add interleave_weighted(*iterables,weights) with one positive index-protocol integer quota per input, rejecting bool/zero/negative/count mismatch. Round-robin in declaration order, at most that source quota per round, exhausted sources leave scheduling while survivors continue. Preserve source order and original identity, support empty and infinite sources via bounded prefix consumption; no random calls or whole-input copies. Propagate source errors and do not close caller-owned sources implicitly.

Deliver real implementation, original-failing public tests at library/tests/test_development_more_itertools_05_dev.py, and English compatibility documentation at library/docs/development-more-itertools-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/more_itertools/more.py
- library/more_itertools/_interleave_weighted.py
- library/tests/test_development_more_itertools_05_dev.py
- library/docs/development-more-itertools-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
