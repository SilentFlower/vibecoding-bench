# Engineering contract: PACKAGING-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add keyword-only strict=False to Marker.evaluate. Default environment overlay behavior remains byte-compatible. Opt-in strict=True starts from no host variables and uses only caller mapping plus existing context defaults (metadata extra="", lock_file empty extras/dependency_groups). Missing referenced variables raise UndefinedEnvironmentName, including RHS variables. Repair supplied python_full_version dev suffix only if present, normalize supplied extra and never mutate caller mappings. Do not query host default_environment in strict mode or invent values for unrelated variables.

Deliver real implementation, original-failing public tests at library/tests/test_development_packaging_02_dev.py, and English compatibility documentation at library/docs/development-packaging-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/packaging/markers.py
- library/tests/test_development_packaging_02_dev.py
- library/docs/development-packaging-02-dev.md
