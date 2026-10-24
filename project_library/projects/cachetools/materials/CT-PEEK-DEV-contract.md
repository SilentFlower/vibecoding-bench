# Engineering contract: CT-PEEK-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Cache.peek(key,default=marker), returning a live value without invoking subclass __getitem__, __missing__, recency/frequency updates or expiry cleanup. Use each cache existing membership semantics, so TTL/TLRU expired entries behave missing; explicit defaults including None are returned, otherwise raise KeyError. Support all built-in cache policies, weighted sizes and custom __missing__ subclasses. Preserve ordinary get/item access behavior and all internal policy accounting.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ct_peek_dev.py and concise English compatibility documentation at library/docs/development-ct-peek-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cachetools/__init__.py
- library/development_tests/test_development_ct_peek_dev.py
- library/docs/development-ct-peek-dev.md
