# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add records.merge_feeds(previous,incoming,*,partial=False) using the delivered explicit entry_identity. Return {result,changes:{added,updated,unchanged,retained}} with incoming order first and previous absent entries retained in old order; absence never deletes. Inputs and nested output are detached. Duplicate identities within either batch raise. Full mode replaces same-id content, partial mode overlays only supplied top-level fields; report actual data changes even if date strings move backward, without guessed conflict winners. Current non-entry metadata overlays prior metadata, and no network fetch or original result mutation occurs.

Deliver meaningful original-failing public regression tests at library/tests/test_development_feedparser_o05_dev.py and concise English compatibility documentation at library/docs/development-feedparser-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedparser/records.py
- library/tests/test_development_feedparser_o05_dev.py
- library/docs/development-feedparser-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
