# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement feedgen.ordering.sorted_feed(feed,*,by="updated",reverse=True,missing="last",since=None,limit=None) and reusable copy_feed(feed,entries). Compare actual updated/published instants across offsets, retain original order on ties, explicitly place or reject missing dates independent of reverse. Inclusive aware since excludes undated entries, nonnegative limit supports zero. Return deeply independent FeedGenerator preserving metadata/extensions/entry content; never reorder or mutate original feed. Reject naive boundaries and invalid modes before changing anything.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_fg_order_dev.py and concise English compatibility documentation at library/docs/development-fg-order-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedgen/ordering.py
- library/development_tests/test_development_fg_order_dev.py
- library/docs/development-fg-order-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
