# Engineering contract: WRAPT-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair wrapt.lru_cache classmethod handling so actual calling class participates in shared cache keys rather than capturing first bound method. Both @lru_cache/@classmethod orders, Base/Derived calls in either order and instance access must return actual cls. Keep ordinary per-instance cache isolation/GC, static/plain functions, cache_info/cache_parameters and shared class cache_clear behavior. Class-key references follow normal functools retention until eviction/clear; do not claim weak class storage.

Deliver real implementation, original-failing public tests at library/tests/test_development_wrapt_01_dev.py, and English compatibility documentation at library/docs/development-wrapt-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wrapt/caching.py
- library/tests/test_development_wrapt_01_dev.py
- library/docs/development-wrapt-01-dev.md
