# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Build deepdiff.merge3.merge3(base,left,right,*,arrays="atomic") on the accepted JSON-tree validation and DeepDiff equality. Return Merge3Result(value,conflicts,complete) recursively combining disjoint dict edits, equal edits, additions and deletions. Explicitly distinguish absent from null. Preserve base at unresolved conflicts with exact component path and independent present/value snapshots for all three sides, never automatically choose left/right. Arrays are atomic business values, so index shifts or divergent arrays conflict; no speculative positional merge. Validate JSON/cycles, reject other array policies and preserve all inputs.

Deliver meaningful original-failing public regression tests at library/tests/test_development_deepdiff_o05_dev.py and concise English compatibility documentation at library/docs/development-deepdiff-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/deepdiff/merge3.py
- library/tests/test_development_deepdiff_o05_dev.py
- library/docs/development-deepdiff-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
