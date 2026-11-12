# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend footnotes(md,*,unique_refs=False) with an explicit compatibility-preserving mode. Each occurrence of one defined footnote gets a unique fnref-N, fnref-N-2,... HTML id and the footnote item links back to all occurrences. Keep one note definition/order/index and expose occurrence metadata in opted-in AST tokens; unknown references remain literal. Reset counts per parsed document, preserve escaping and legacy default HTML/AST exactly, and verify document reuse plus interaction with directory extraction.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ms_unique_footnotes_dev.py and concise English compatibility documentation at library/docs/development-ms-unique-footnotes-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/mistune/plugins/footnotes.py
- library/development_tests/test_development_ms_unique_footnotes_dev.py
- library/docs/development-ms-unique-footnotes-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
