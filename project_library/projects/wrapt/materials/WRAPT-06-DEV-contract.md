# Engineering contract: WRAPT-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend delivered canonical_cache with cache_invalidate(*args,**kwargs) using the SAME make_key/signature/default/custom-key path as reads. Return True only when existing entry deleted; missing returns False, invalid call/key errors propagate. Preserve all unrelated entries and hit/miss statistics, per-method-self identity and custom business IDs. Run invalidation under same computation RLock so a completed call cannot later silently refill invalidated value; explicitly no cancellation of already-running user code. Do not call cache_clear internally or reset all stats. Keep existing default/cache_clear behavior.

Deliver real implementation, original-failing public tests at library/tests/test_development_wrapt_06_dev.py, and English compatibility documentation at library/docs/development-wrapt-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wrapt/canonical_cache.py
- library/tests/test_development_wrapt_06_dev.py
- library/docs/development-wrapt-06-dev.md
