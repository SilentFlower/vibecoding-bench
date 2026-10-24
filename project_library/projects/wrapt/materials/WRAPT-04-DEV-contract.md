# Engineering contract: WRAPT-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add separate wrapt.ttl_cache.ttl_cache(ttl,maxsize=128,clock=monotonic). Use finite explicit nonnegative TTL from successful computation COMPLETION, maxsize bounded LRU and global expired-entry purge on call/info; zero TTL/maxsize disables storing. Injectable clock for exact deterministic tests, reject nonfinite/backward clock or invalid budget. Exceptions never cached, results maintain identity, cache_info/cache_clear defined. Thread RLock serializes computation/clear; no cross-key concurrency promise. Hashable args/sorted kwargs keys include method self with normal cache retention; preserve existing lru_cache unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_wrapt_04_dev.py, and English compatibility documentation at library/docs/development-wrapt-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wrapt/ttl_cache.py
- library/tests/test_development_wrapt_04_dev.py
- library/docs/development-wrapt-04-dev.md
