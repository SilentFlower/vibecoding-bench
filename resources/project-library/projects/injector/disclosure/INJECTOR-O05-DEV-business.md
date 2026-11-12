# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add evict(key)->bool and clear()->count to actual SingletonScope and ThreadLocalScope. Remove cached Providers under existing singleton lock, leave binding definitions and externally held objects untouched, perform no implicit close or dependency cascade. ThreadLocalScope operations affect only the calling thread, never another thread cache. Nonexistent keys and repeated clear are safe; subsequent actual Injector.get reconstructs only invalidated targets while unrelated singleton identity remains. For parent-shared instances document scope ownership and require calling the actual owning scope rather than promising child-local invalidation refreshes parent cache.

Deliver meaningful original-failing public regression tests at library/tests/test_development_injector_o05_dev.py and concise English compatibility documentation at library/docs/development-injector-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/injector/__init__.py
- library/tests/test_development_injector_o05_dev.py
- library/docs/development-injector-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
