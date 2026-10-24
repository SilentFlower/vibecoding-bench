# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add funcy.relations.join_by(left,right,left_key,right_key=None,*,how="inner") and frozen JoinPair(left,right,left_present,right_present). Use exact string fields or real Funcy make_func index/callable selectors, materialize right once then lazily consume left, producing every duplicate-key Cartesian pair in left/right order. Support inner/left/full and append unmatched right rows in original order. None is a legal key/record distinguished from absence by presence flags, unhashable keys and callback/input errors propagate. Never mutate/merge record fields or silently overwrite duplicates; state right-side memory cost and leave existing collection join/group_by untouched.

Deliver meaningful original-failing public regression tests at library/tests/test_development_funcy_o05_dev.py and concise English compatibility documentation at library/docs/development-funcy-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/funcy/relations.py
- library/tests/test_development_funcy_o05_dev.py
- library/docs/development-funcy-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
