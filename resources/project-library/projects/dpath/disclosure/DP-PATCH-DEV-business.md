# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement dpath.patches.apply_edits(root,operations) using completed get_exact for typed literal paths. Materialize operations first and work on a deep copy. Support add/replace/remove/test; dictionary add sets a key, replace/remove require it, list add inserts at 0..len and remove compacts. Reject bool/negative list indices; test compares recursive types and values so True differs from 1. Empty path may test or replace/add root, but cannot remove root. Any later invalid operation, failed test or enumeration error leaves original unchanged; copy incoming mutable values and do not reinterpret paths as globs.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_dp_patch_dev.py and concise English compatibility documentation at library/docs/development-dp-patch-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dpath/patches.py
- library/development_tests/test_development_dp_patch_dev.py
- library/docs/development-dp-patch-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
