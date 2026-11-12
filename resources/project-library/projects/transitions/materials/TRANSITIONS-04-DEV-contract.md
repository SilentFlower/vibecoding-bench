# Engineering contract: TRANSITIONS-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add Machine.preview_event(model,trigger) for core synchronous FLAT Machine, bound model required. Return current state, ordered candidate source/dest, stable ordinal and condition index/callback descriptor/target (unless false), callback descriptors and runnable="unknown". Do not resolve string callbacks, access callback properties, execute prepare/guards/before/after or change state. Unknown trigger returns no candidates. Preserve internal None/reflexive/wildcard-expanded paths. No hierarchical/parallel/async completeness promise or fabricated allowed=True.

Deliver real implementation, original-failing public tests at library/tests/test_development_transitions_04_dev.py, and English compatibility documentation at library/docs/development-transitions-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/transitions/core.py
- library/tests/test_development_transitions_04_dev.py
- library/docs/development-transitions-04-dev.md
