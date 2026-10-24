# Engineering contract: CHARDET-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement chardet.files.detect_file(source, *, preserve_position=True, chunk_size=65536, max_bytes=None) on the delivered split-BOM detector. Support text/PathLike paths and caller-owned binary streams, short reads and exact nonnegative byte budgets without lookahead. Restore seekable caller positions on success/failure, never close caller streams, close owned files, and report actual read_bytes/eof/budget_exhausted without claiming an inspected prefix validates the whole file. Zero budget performs no reads; nonseekable preserving mode and text reads fail explicitly.

Deliver meaningful original-failing public regression tests at library/tests/test_development_chardet_o03_dev.py and concise English compatibility documentation at library/docs/development-chardet-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/chardet/files.py
- library/tests/test_development_chardet_o03_dev.py
- library/docs/development-chardet-o03-dev.md
