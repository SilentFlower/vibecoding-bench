# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement deepdiff.merge.deep_merge(left,right,*,lists="replace",conflicts="right"), MergeConflict(path), validate_json_tree and actual-DeepDiff-based json_equal. Recursively union dict keys preserving left then right order; lists explicitly replace or append with duplicate preservation; conflicting leaves/types choose right/left or raise at exact tuple path. Preserve bool-vs-int and None semantics, input independence, reject nonstring dict keys, unsupported objects, nonfinite floats and cycles while allowing acyclic shared references. Do not change Delta or merge arbitrary object attributes; prove native Delta still performs target replacement.

Deliver meaningful original-failing public regression tests at library/tests/test_development_deepdiff_o04_dev.py and concise English compatibility documentation at library/docs/development-deepdiff-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/deepdiff/merge.py
- library/tests/test_development_deepdiff_o04_dev.py
- library/docs/development-deepdiff-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
