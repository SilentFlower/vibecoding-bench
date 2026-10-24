# Engineering contract: WRAPT-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add explicit wrapt.async_cache.async_lru_cache(maxsize=128) for coroutine functions, storing only successful completed values in per-running-loop bounded LRU. Repeat await same call works, exceptions and cancellation never cache; clear during in-flight compute advances generation so its later success returns only to caller without repopulating cleared cache. Expose current-loop cache_info/cache_clear, preserve metadata and descriptor binding through normal async function. Concurrent same-key misses explicitly may compute separately, no singleflight. Keys are hashable args+sorted kwargs including method self, normal result/argument retention until eviction/clear. Default synchronous lru_cache unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_wrapt_03_dev.py, and English compatibility documentation at library/docs/development-wrapt-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wrapt/async_cache.py
- library/tests/test_development_wrapt_03_dev.py
- library/docs/development-wrapt-03-dev.md
