# Engineering contract: WRAPT-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add independent wrapt.canonical_cache.canonical_cache(maxsize=128,typed=False,key_func=None). inspect.signature.bind/apply_defaults before key creation so equivalent positional/keyword/explicit-default calls share, varargs remain ordered and varkw keys sort deterministically. typed mode includes direct bound value types. Custom key_func receives BoundArguments after signature validation and may extract id from unhashable dict; collisions are explicit caller policy. Default unhashable values fail, never deepcopy/serialize arbitrary inputs. Bounded LRU, cache_info/clear, exception propagation and ordinary metadata/descriptor binding; synchronous RLock serializes. Existing lru_cache key behavior unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_wrapt_05_dev.py, and English compatibility documentation at library/docs/development-wrapt-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wrapt/canonical_cache.py
- library/tests/test_development_wrapt_05_dev.py
- library/docs/development-wrapt-05-dev.md
