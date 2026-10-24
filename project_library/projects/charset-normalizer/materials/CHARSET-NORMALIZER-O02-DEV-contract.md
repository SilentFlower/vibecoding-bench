# Engineering contract: CHARSET-NORMALIZER-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement charset_normalizer.streams.from_stream(stream, *, max_bytes, read_size=65536, preserve_position=True, **options). Never read(-1), retain at most the explicit nonnegative budget, handle short reads and report actual read_bytes/eof/budget_exhausted with real from_bytes matches. Restore seekable caller positions even on errors and never close caller streams; nonseekable preservation/text reads/invalid bounds fail clearly. Zero budget must not read, and a limited prefix must not be represented as whole-source validation.

Deliver meaningful original-failing public regression tests at library/tests/test_development_charset_normalizer_o02_dev.py and concise English compatibility documentation at library/docs/development-charset-normalizer-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/charset_normalizer/streams.py
- library/tests/test_development_charset_normalizer_o02_dev.py
- library/docs/development-charset-normalizer-o02-dev.md
