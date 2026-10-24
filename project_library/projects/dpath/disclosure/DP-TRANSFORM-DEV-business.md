# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement dpath.transforming.transform_existing(root,transform,*,predicate=None), using completed walk_paths and get_exact rather than glob strings. Evaluate only original snapshot leaves (including empty containers), pass typed tuple path and detached value to callbacks, write replacements into a deep-copied result and never revisit newly generated content. Predicate is optional; late callback or cycle errors propagate while original objects remain unchanged, including callback mutations of supplied values. Root-leaf replacement works; preserve shared-copy alias semantics and source traversal order.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_dp_transform_dev.py and concise English compatibility documentation at library/docs/development-dp-transform-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dpath/transforming.py
- library/development_tests/test_development_dp_transform_dev.py
- library/docs/development-dp-transform-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
