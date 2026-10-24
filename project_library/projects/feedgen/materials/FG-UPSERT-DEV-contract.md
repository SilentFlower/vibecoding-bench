# Engineering contract: FG-UPSERT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement feedgen.upsert.upsert_entries(feed,entries) and frozen UpsertResult(added,updated). Use actual FeedGenerator/FeedEntry APIs. Validate all existing/incoming entries have unique nonempty string IDs before mutation; invalid late input or generator failure preserves original entries. Replace matching IDs at their original position with supplied entry objects, append new IDs in incoming order, retain unrelated exact entry objects and metadata/extensions. Do not merge entries by title or destructively edit old entry fields. Empty input is valid; duplicate old IDs are explicit errors.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_fg_upsert_dev.py and concise English compatibility documentation at library/docs/development-fg-upsert-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedgen/upsert.py
- library/development_tests/test_development_fg_upsert_dev.py
- library/docs/development-fg-upsert-dev.md
