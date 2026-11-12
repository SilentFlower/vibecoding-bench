# Engineering contract: TRANSITIONS-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair remove_transition list normalization to inspect each source/dest element, accepting existing string/single State/Enum and mixed lists. Remove only selected edge combinations, preserve unrelated paths, wildcard/empty selections, and current final-event/model-method cleanup. Do not inspect container.name, silently remove all transitions, change unknown trigger error behavior or alter live transition execution.

Deliver real implementation, original-failing public tests at library/tests/test_development_transitions_02_dev.py, and English compatibility documentation at library/docs/development-transitions-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/transitions/core.py
- library/tests/test_development_transitions_02_dev.py
- library/docs/development-transitions-02-dev.md
