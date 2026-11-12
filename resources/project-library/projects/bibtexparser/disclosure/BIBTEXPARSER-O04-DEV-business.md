# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bibtexparser.keywords.SplitKeywords and MergeKeywords as opt-in non-mutating BlockMiddleware classes. Split only top-level single-character delimiters, preserving nested braces and backslash-escaped delimiters, with explicit keep_empty behavior. Reject unbalanced braces, preserve keyword order/duplicates and support custom delimiters. Merge actual string lists back to reversible strings, protecting unbraced delimiter-containing items. Do not reuse author splitting or change default parse/write stacks.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bibtexparser_o04_dev.py and concise English compatibility documentation at library/docs/development-bibtexparser-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bibtexparser/keywords.py
- library/tests/test_development_bibtexparser_o04_dev.py
- library/docs/development-bibtexparser-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
