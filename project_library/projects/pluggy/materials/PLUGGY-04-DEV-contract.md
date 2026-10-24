# Engineering contract: PLUGGY-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add HookCaller.set_history_limit(None|nonnegative int) and clear_history(predicate=None)->removed count, only for historic hooks. Default unlimited remains unchanged. Retain newest N events for future replay, limit zero still delivers live calls but stores none; predicate receives a shallow kwargs copy and must be side-effect free. Selector errors before commit leave history unchanged. Historic replay iterates a stable start snapshot so clear/append during replay affect future replays without skipping or infinite growth in the current replay. Subset callers share the original history policy. Preserve previously accepted call-time shallow snapshots and result callbacks; clearing never retracts external effects.

Deliver real implementation, original-failing public tests at library/tests/test_development_pluggy_04_dev.py, and English compatibility documentation at library/docs/development-pluggy-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pluggy/_caller.py
- library/tests/test_development_pluggy_04_dev.py
- library/docs/development-pluggy-04-dev.md
