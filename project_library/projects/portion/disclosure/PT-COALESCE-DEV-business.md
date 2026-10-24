# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Interval.coalesce(max_gap, metric=None, *, report=False). Bridge consecutive normalized atomic pieces when their endpoint distance is at most a nonnegative explicit tolerance, using subtraction by default or a caller metric(lower_endpoint, upper_endpoint). Preserve external bounds and class, never mutate the source, and optionally return the exact added gap intervals. Support numeric/Decimal and timedelta distances, zero-width missing points, empty input, and propagate metric errors; reject negative/NaN tolerance and negative metric results. This is explicitly approximate and must not change exact union/overlap semantics.

Deliver meaningful original-failing public regression tests at library/tests/test_development_pt_coalesce_dev.py and concise English compatibility documentation at library/docs/development-pt-coalesce-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/portion/interval.py
- library/tests/test_development_pt_coalesce_dev.py
- library/docs/development-pt-coalesce-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
