# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add explicit wrapt.weak_cache.weak_method_cache(maxsize=128,typed=False) using real wrapt descriptor/decorator binding and WeakFunctionProxy. Maintain id+weakref-verified per-instance caches without requiring instance hash/equality or __dict__; weak callbacks remove exact matching entry, bound methods must not strongly retain instance. Expose cache_count() and cache_clear(instance=None). Reject nonweakrefable/class/plain usage clearly, preserve method results/exceptions and functools argument/typed semantics. Thread-safe cache creation, no singleflight promise. Cached result or arguments that themselves retain self follow normal retention and are excluded from weak-lifetime guarantee. Existing lru_cache unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_wrapt_02_dev.py, and English compatibility documentation at library/docs/development-wrapt-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wrapt/weak_cache.py
- library/tests/test_development_wrapt_02_dev.py
- library/docs/development-wrapt-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
