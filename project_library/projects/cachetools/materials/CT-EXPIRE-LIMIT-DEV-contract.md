# Engineering contract: CT-EXPIRE-LIMIT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend TTLCache.expire(time=None,*,limit=None) with a validated nonnegative nonboolean integer limit. Return/remove at most that many expired pairs in original expiry order; zero removes nothing and None preserves exact legacy full cleanup. Repeated bounded calls must eventually remove all expired items without corrupting linked-list/LRU/weighted-size accounting or touching live entries. Invalid limits fail before timer sampling or mutation. Ordinary len/set/popitem still invoke default full expiry.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ct_expire_limit_dev.py and concise English compatibility documentation at library/docs/development-ct-expire-limit-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/cachetools/__init__.py
- library/development_tests/test_development_ct_expire_limit_dev.py
- library/docs/development-ct-expire-limit-dev.md
