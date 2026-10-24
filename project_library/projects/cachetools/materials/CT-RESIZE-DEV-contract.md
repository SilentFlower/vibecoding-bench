# Engineering contract: CT-RESIZE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Cache.resize(maxsize) for built-in policies. Validate a nonnegative real int/float excluding bool/NaN; allow positive infinity. Perform normal expiry cleanup for timed caches, then evict through their original popitem policy until currsize fits, update maxsize and return a tuple of capacity-evicted pairs (not expired pairs). Preserve weighted sizing, growth/no-op behavior, subsequent insertion semantics and zero capacity. Validation must happen before any cleanup or mutation; do not rebuild caches or reset policy history.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ct_resize_dev.py and concise English compatibility documentation at library/docs/development-ct-resize-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cachetools/__init__.py
- library/development_tests/test_development_ct_resize_dev.py
- library/docs/development-ct-resize-dev.md
