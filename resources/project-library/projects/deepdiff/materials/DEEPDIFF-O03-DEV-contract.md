# Engineering contract: DEEPDIFF-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add explicit datetime.timezone value handling in actual DeepDiff dispatch and DeepHash preparation. Compare native fixed offsets (including negative, fractional hour and microsecond offsets), ignoring display names exactly like Python equality. Different offsets report values_changed, including nested and ignore_order structures, and canonical hashes must agree with equality. Preserve dynamic tzinfo/other-class type rules and existing datetime normalization; do not claim arbitrary timezone-rule comparison.

Deliver meaningful original-failing public regression tests at library/tests/test_development_deepdiff_o03_dev.py and concise English compatibility documentation at library/docs/development-deepdiff-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/deepdiff/diff.py
- library/deepdiff/deephash.py
- library/tests/test_development_deepdiff_o03_dev.py
- library/docs/development-deepdiff-o03-dev.md
