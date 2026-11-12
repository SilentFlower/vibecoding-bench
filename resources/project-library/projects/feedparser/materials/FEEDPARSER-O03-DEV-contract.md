# Engineering contract: FEEDPARSER-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add public immutable DateHandlerRegistry(handlers=(), include_builtin=True) and parse(..., date_handlers=registry). Apply through actual shared _parse_date paths with ContextVar scoping/reset on every exit, preserving default global registerDateHandler behavior and built-in order. Freeze/deduplicate custom handler identities, accept only nine nonbool integer tuple/list returns, skip mismatches/declared custom failures and continue to later handlers; never catch BaseException cancellation. Interleaved/concurrent/nested parsing must not leak registries. Use real RSS/JSON date parsing, not a separate unused date utility or global list swapping.

Deliver meaningful original-failing public regression tests at library/tests/test_development_feedparser_o03_dev.py and concise English compatibility documentation at library/docs/development-feedparser-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedparser/datetimes/__init__.py
- library/feedparser/api.py
- library/feedparser/__init__.py
- library/tests/test_development_feedparser_o03_dev.py
- library/docs/development-feedparser-o03-dev.md
