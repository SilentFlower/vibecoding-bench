# Engineering contract: FEEDPARSER-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add feedparser.readers.entry_text(entry,*,prefer=(text/plain,text/html,application/xhtml+xml),languages=(),strip_html=True). Select existing nonempty local content with MIME priority then declared language order/source order, accepting native content lists and legacy JSON single-content dict; normalize text/html/xhtml aliases. Fall back to real summary_detail or summary only when no usable content. Return text plus original value/type/language/source/index, leaving entry unchanged. Optional limited HTML text extraction preserves block/break/entity order and excludes script/style text; do not claim sanitization. Never fetch src, invent a body from title, accept unknown types silently or generate a summary.

Deliver meaningful original-failing public regression tests at library/tests/test_development_feedparser_o06_dev.py and concise English compatibility documentation at library/docs/development-feedparser-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedparser/readers.py
- library/tests/test_development_feedparser_o06_dev.py
- library/docs/development-feedparser-o06-dev.md
