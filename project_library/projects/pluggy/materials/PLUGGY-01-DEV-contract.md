# Engineering contract: PLUGGY-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair HookCaller.call_historic to apply specification defaults then shallow-copy the kwargs mapping before recording/executing. Deferred plugin replay observes call-time keys/values even if caller later replaces/clears the outer mapping. Nested mutable objects remain intentionally shared by identity; do not deepcopy user values or callbacks. Preserve custom Mapping input, empty mappings, defaults, result_callback behavior, existing call ordering and nonhistoric hooks.

Deliver real implementation, original-failing public tests at library/tests/test_development_pluggy_01_dev.py, and English compatibility documentation at library/docs/development-pluggy-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pluggy/_caller.py
- library/tests/test_development_pluggy_01_dev.py
- library/docs/development-pluggy-01-dev.md
