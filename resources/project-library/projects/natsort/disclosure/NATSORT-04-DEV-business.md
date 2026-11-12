# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add natsort.merge.merge_sorted(*iterables,key=None,alg=ns.DEFAULT,reverse=False,strict=True). Lazily merge already naturally ordered streams with original rows preserved, equal keys stable by stream then local order, one natural-key calculation per consumed row, and optional monotonicity validation matching reverse. Empty/infinite streams and early close must not cause eager reads; caller owns original streams. Reject disorder rather than silently sorting it; propagate callbacks and source errors.

Deliver real implementation, original-failing public tests at library/tests/test_development_natsort_04_dev.py, and English compatibility documentation at library/docs/development-natsort-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/natsort/merge.py
- library/tests/test_development_natsort_04_dev.py
- library/docs/development-natsort-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
