# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add Machine.dispatch_report(trigger,*args,collect_errors=True,**kwargs) for nonqueued synchronous machines. Snapshot model declaration order, call actual bound trigger once each, return ordered tuple rows with ordinal/model identity/source/dest/result/status/error_type. False is rejected, True succeeded, exception failed without leaking error message. Collect mode continues, fail-fast stops after error row; prior successful states are not rolled back. Reject queued and async triggers before execution rather than call admission True final success. Existing dispatch bool unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_transitions_05_dev.py, and English compatibility documentation at library/docs/development-transitions-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/transitions/core.py
- library/tests/test_development_transitions_05_dev.py
- library/docs/development-transitions-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
