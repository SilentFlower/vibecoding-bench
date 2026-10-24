# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add TTLCache.remaining(key,*,time=None), returning expires-now using explicit time or one timer sample. Preserve timer arithmetic types including datetime/timedelta. Missing and expired/equal-boundary keys raise KeyError, with no physical expiry removal, value loading or LRU reordering. Do not extend expiry or alter __getitem__, ttl, pickle or capacity semantics; verify reads do not protect cold entries from eviction.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ct_remaining_dev.py and concise English compatibility documentation at library/docs/development-ct-remaining-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cachetools/__init__.py
- library/development_tests/test_development_ct_remaining_dev.py
- library/docs/development-ct-remaining-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
