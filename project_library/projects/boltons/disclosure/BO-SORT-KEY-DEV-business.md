# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix iterutils.untyped_sorted so a supplied key is evaluated exactly once per input occurrence before comparisons, matching sorted key semantics. Preserve heterogeneous-type fallback order, stable equal keys, reverse and falsey callable support; validate noncallable keys, propagate key/comparison errors and leave input unchanged. Do not cache by object identity or return wrappers instead of original objects.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_bo_sort_key_dev.py and concise English compatibility documentation at library/docs/development-bo-sort-key-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/boltons/iterutils.py
- library/development_tests/test_development_bo_sort_key_dev.py
- library/docs/development-bo-sort-key-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
