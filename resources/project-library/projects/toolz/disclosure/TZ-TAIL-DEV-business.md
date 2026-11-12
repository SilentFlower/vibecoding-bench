# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair tail(n, seq) so n=0 returns an empty result of the normal slice type for sliceable inputs and an empty tuple for iterator inputs without reading them. Reject negative index-protocol counts consistently with ValueError before consuming input. Preserve positive tail, last, index-protocol integers, top-level/curried/tlz APIs and all frozen tests. Do not eagerly materialize input or special-case the public example.

Deliver meaningful original-failing public regression tests at library/toolz/tests/test_development_tz_tail_dev.py and concise English compatibility documentation at library/docs/development-tz-tail-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/toolz/itertoolz.py
- library/toolz/tests/test_development_tz_tail_dev.py
- library/docs/development-tz-tail-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
