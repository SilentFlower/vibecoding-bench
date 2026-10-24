# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement cssselect.cache.SelectorCache(capacity=128) with translate(css, *, mode="xml", xhtml=False, prefix=...), stats(), clear(reset_stats=False). Cache actual builtin XML/HTML translation by complete CSS and every supported mode/XHTML/prefix field; no arbitrary custom translator sharing without fingerprint. Enforce positive non-bool capacity, true access-order LRU, isolated instances, fresh stats and lock-protected consistent concurrent access. Count failures as misses but never cache them. Preserve native parse/translation exceptions, old uncached APIs, and explicit clear/stat-reset semantics.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cssselect_o03_dev.py and concise English compatibility documentation at library/docs/development-cssselect-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cssselect/cache.py
- library/tests/test_development_cssselect_o03_dev.py
- library/docs/development-cssselect-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
