# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add natsort.cached.cached_natsort_keygen(key=None, alg=ns.DEFAULT, maxsize=128). Each factory owns an independent bounded LRU and exposes cache_info/cache_clear; hashable values are type-separated, unhashable values bypass caching, and exceptions are not cached. Output must match the original configured natsort_keygen. Reject negative/noninteger capacities and active caching of global LOCALE strategies; maxsize=0 disables storage. Mutable external key policy requires explicit cache_clear or a new factory. Default natsort APIs remain unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_natsort_02_dev.py, and English compatibility documentation at library/docs/development-natsort-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/natsort/cached.py
- library/tests/test_development_natsort_02_dev.py
- library/docs/development-natsort-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
