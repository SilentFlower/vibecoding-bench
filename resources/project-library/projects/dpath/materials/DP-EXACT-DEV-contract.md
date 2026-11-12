# Engineering contract: DP-EXACT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement dpath.exact.get_exact(root,segments,default=marker). Paths are finite component iterables, never plain strings; mapping keys retain actual hashable types and punctuation, list indices are nonnegative int excluding bool. Empty path returns root identity. Missing key/index returns an explicit default or raises original error, while invalid traversal/type errors propagate. Do not interpret glob characters, coerce "1" to integer, trigger defaultdict creation, or mutate input; preserve old dpath.get.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_dp_exact_dev.py and concise English compatibility documentation at library/docs/development-dp-exact-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dpath/exact.py
- library/development_tests/test_development_dp_exact_dev.py
- library/docs/development-dp-exact-dev.md
