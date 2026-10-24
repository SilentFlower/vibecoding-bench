# Engineering contract: CHARSET-NORMALIZER-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Make CharsetMatch retain immutable payload bytes so caller bytearray mutation cannot diverge raw bytes from cached text. Add charset_normalizer.buffers.from_buffer(buffer, **options) for continuous buffer protocol input, explicitly snapshot non-bytes, preserve caller view ownership and return matches/copied/nbytes. Reject noncontiguous/released/nonbuffer inputs clearly, support empty/read-only/writable buffers and delegate detection options to actual from_bytes. Do not promise universal zero-copy decoding or change existing immutable bytes results.

Deliver meaningful original-failing public regression tests at library/tests/test_development_charset_normalizer_o01_dev.py and concise English compatibility documentation at library/docs/development-charset-normalizer-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/charset_normalizer/models.py
- library/src/charset_normalizer/buffers.py
- library/tests/test_development_charset_normalizer_o01_dev.py
- library/docs/development-charset-normalizer-o01-dev.md
