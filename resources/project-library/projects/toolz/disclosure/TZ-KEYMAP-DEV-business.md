# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend keymap with keyword-only collision='last' and combine=None. Preserve default last-value semantics; add first, error with original-key context, and ordered combine(existing, incoming) policies. Transform each original key exactly once, preserve input mapping and factory/insertion order, propagate unhashable-key and callback errors, validate policies and expose behavior through curried/tlz without changing itemmap/merge semantics.

Deliver meaningful original-failing public regression tests at library/toolz/tests/test_development_tz_keymap_dev.py and concise English compatibility documentation at library/docs/development-tz-keymap-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/toolz/dicttoolz.py
- library/toolz/tests/test_development_tz_keymap_dev.py
- library/docs/development-tz-keymap-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
