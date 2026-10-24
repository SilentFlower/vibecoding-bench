# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement inflect.counted.counted(engine,noun,count,*,words=False,zero="0",separator=" "). Require nonempty noun and nonnegative integer count (bool rejected), real plural_noun with explicit count and cloned current custom rules/classical options. Support custom zero label, number_to_words and separator. Persistent count, number spelling scratch state and user rules of original engine remain unchanged on success or failure. Zero grammatical form follows actual current classical mode; do not hardcode English singular/plural suffixes.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_if_counted_dev.py and concise English compatibility documentation at library/docs/development-if-counted-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/inflect/counted.py
- library/development_tests/test_development_if_counted_dev.py
- library/docs/development-if-counted-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
