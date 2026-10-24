# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add dissoc_in(d, keys, factory=dict, *, strict=False, prune=False). Copy only affected mapping branches and delete the leaf, retain untouched references and input data, preserve empty ancestors by default or prune them explicitly. Missing paths return a shallow root copy unless strict=True; empty paths raise ValueError and scalar ancestors raise TypeError. Support one-shot key paths, mapping factories and toolz/curried/tlz exports in the frozen environment. Keep existing dissoc/assoc_in/update_in semantics unchanged.

Deliver meaningful original-failing public regression tests at library/toolz/tests/test_development_tz_dissoc_in_dev.py and concise English compatibility documentation at library/docs/development-tz-dissoc-in-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/toolz/dicttoolz.py
- library/toolz/curried/__init__.py
- library/toolz/tests/test_development_tz_dissoc_in_dev.py
- library/docs/development-tz-dissoc-in-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
