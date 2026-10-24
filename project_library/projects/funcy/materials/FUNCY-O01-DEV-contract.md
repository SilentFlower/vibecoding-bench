# Engineering contract: FUNCY-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix actual cached_property/cached_readonly with __set_name__ and a shared real cache-key policy, so value=cached_property(calculate) caches under value and never shadows calculate. Preserve ordinary decorator behavior, inherited descriptors, class access, independent instances and cached_property manual set/delete while readonly remains protected. Reject the same descriptor bound under different names explicitly, retain legacy function-name fallback for manually unbound descriptors and fail clearly on no-__dict__ objects. Demonstrate evaluation count and method identity, not only metadata.

Deliver meaningful original-failing public regression tests at library/tests/test_development_funcy_o01_dev.py and concise English compatibility documentation at library/docs/development-funcy-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/funcy/objects.py
- library/tests/test_development_funcy_o01_dev.py
- library/docs/development-funcy-o01-dev.md
