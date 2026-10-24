# Engineering contract: PYDASH-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pydash.json_patch.patch_paths and top-level export, reusing the accepted explicit Pointer implementation. Execute ordered set/remove/test on a deep JSON copy and return it only on success; source and operation value containers remain isolated. Respect overlapping paths, list deletion shifts, escaped keys and root set/test. Root removal/unknown ops/missing values/late test failures/invalid parents fail without source changes. No arbitrary-object transaction or concurrency promise; existing mutating set_/unset unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydash_05_dev.py, and English compatibility documentation at library/docs/development-pydash-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pydash/json_patch.py
- library/src/pydash/__init__.py
- library/tests/test_development_pydash_05_dev.py
- library/docs/development-pydash-05-dev.md
