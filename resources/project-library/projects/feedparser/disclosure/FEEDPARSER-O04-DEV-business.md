# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add feedparser.records.entry_identity for actual parsed entry mappings. Prefer a nonempty native string id with reliable=True; otherwise compute deterministic SHA256 from explicit selected actual fields with configurable NFC string normalization, canonical JSON and reliable=False/source=fields metadata. Never inject an id, read compatibility alias fallbacks as real facts, strip tracking parameters or identify entries merely by similar titles. Reject missing usable data, duplicate/invalid field names, nonstring native ids and unsupported/nonfinite JSON values explicitly. Preserve inputs, distinguish equal titles with different links and document fallback collision/stability scope.

Deliver meaningful original-failing public regression tests at library/tests/test_development_feedparser_o04_dev.py and concise English compatibility documentation at library/docs/development-feedparser-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedparser/records.py
- library/tests/test_development_feedparser_o04_dev.py
- library/docs/development-feedparser-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
