# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Interval.measure(metric, *, start=0): invoke the caller-supplied metric exactly once for each atomic interval in order and combine with addition beginning at start. The metric receives actual bound openness and endpoints so the same protocol can express continuous duration or bounded integer cardinality; no generic endpoint subtraction is implicit. Empty intervals return start without callbacks; preserve Decimal/timedelta result types with an appropriate identity, propagate callback errors and let metrics explicitly reject unbounded domains. Preserve len as the number of atomic pieces, subclasses, laziness of existing APIs and every frozen test.

Deliver meaningful original-failing public regression tests at library/tests/test_development_pt_measure_dev.py and concise English compatibility documentation at library/docs/development-pt-measure-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/portion/interval.py
- library/tests/test_development_pt_measure_dev.py
- library/docs/development-pt-measure-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
