# Engineering contract: PYTHON-LIQUID-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair CachingLoaderMixin.load_async argument ordering: cache_key belongs to _check_cache_async and original name belongs to underlying source load_async. Preserve namespace resolution kwargs over context, separate namespaces, shared sync/async same-key cache identity, auto_reload and no-namespace behavior. Missing source must remain TemplateNotFoundError. Do not make synthetic namespace/name templates or disable caching to mask the defect.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_liquid_01_dev.py, and English compatibility documentation at library/docs/development-python-liquid-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/liquid/builtin/loaders/mixins.py
- library/tests/test_development_python_liquid_01_dev.py
- library/docs/development-python-liquid-01-dev.md
