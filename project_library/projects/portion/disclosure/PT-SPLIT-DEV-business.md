# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Interval.split(points, *, ownership='right') returning an ordered tuple of same-class nonempty atomic intervals. Sort/deduplicate a finite one-shot cut iterable, ignore cuts outside the interior of each atomic part and explicitly assign internal cut points to the right or left partition. Preserve original exterior openness, gaps, empty/singleton intervals and comparable date endpoints. Returned pieces must be pairwise disjoint and their union exactly the input; do not change Interval normalization to keep partitions apart.

Deliver meaningful original-failing public regression tests at library/tests/test_development_pt_split_dev.py and concise English compatibility documentation at library/docs/development-pt-split-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/portion/interval.py
- library/tests/test_development_pt_split_dev.py
- library/docs/development-pt-split-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
