# Engineering contract: TZ-UPDATE-ONLY-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend update_in with keyword-only create=True. With create=False, update only fully existing paths; if any key is absent, return a shallow root copy without calling func or creating branches. Existing None counts as present. Preserve input data and untouched branch identities, one-shot paths, factory types, curried exports, callback exceptions and default upsert behavior. Reject an empty only-update path with ValueError and invalid create types with TypeError.

Deliver meaningful original-failing public regression tests at library/toolz/tests/test_development_tz_update_only_dev.py and concise English compatibility documentation at library/docs/development-tz-update-only-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/toolz/dicttoolz.py
- library/toolz/tests/test_development_tz_update_only_dev.py
- library/docs/development-tz-update-only-dev.md
