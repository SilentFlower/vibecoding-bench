# Engineering contract: PYTHON-LIQUID-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add liquid.versioned_loader.VersionedDictLoader implementing real BaseLoader source/load/load_async contracts with explicit update/delete/snapshot, owned initial source mapping, monotonic per-name revisions, same-content no-op, bounded LRU compiled cache and in-memory RLock atomic loads. Old BoundTemplate and snapshot stay old; only changed name invalidates, missing loads/delete raise TemplateNotFoundError. Separate environments by actual environment object, and explicit globals loads do not mutate cached shared template globals. Async memory loads use same atomic operation without await split. Leave existing mutable DictLoader/CachingDictLoader behavior unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_liquid_02_dev.py, and English compatibility documentation at library/docs/development-python-liquid-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/liquid/versioned_loader.py
- library/tests/test_development_python_liquid_02_dev.py
- library/docs/development-python-liquid-02-dev.md
