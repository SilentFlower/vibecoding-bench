# Engineering contract: CHARSET-NORMALIZER-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement charset_normalizer.compressed.from_compressed_path(path, *, format, max_bytes, read_size=65536, **options). Use actual gzip/bz2/xz readers with a required decompressed-byte budget (at most one extra sentinel to detect overflow), then delegate complete payload detection to from_bytes. Report compressed/decoded byte sizes, support empty and multistream gzip, and fail on corruption/truncation/overrun without partial-success claims or modifying source files. Never auto-guess compressed formats or add remote I/O.

Deliver meaningful original-failing public regression tests at library/tests/test_development_charset_normalizer_o04_dev.py and concise English compatibility documentation at library/docs/development-charset-normalizer-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/charset_normalizer/compressed.py
- library/tests/test_development_charset_normalizer_o04_dev.py
- library/docs/development-charset-normalizer-o04-dev.md
