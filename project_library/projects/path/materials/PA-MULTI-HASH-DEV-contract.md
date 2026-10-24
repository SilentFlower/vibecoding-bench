# Engineering contract: PA-MULTI-HASH-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Path.read_hashes(algorithms,*,chunk_size=8192,hex=True), returning insertion-ordered algorithm->digest mapping. Materialize/deduplicate algorithm names, validate fixed-size hash objects and positive integer chunk size before opening, read one stream once and update every digest for each bounded chunk. Support empty/binary/large files and raw digest output, close stream on read errors and propagate them. Reject empty algorithms, bool sizes, unknown hashes and XOFs requiring a length; preserve old hash APIs.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_pa_multi_hash_dev.py and concise English compatibility documentation at library/docs/development-pa-multi-hash-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/path/__init__.py
- library/development_tests/test_development_pa_multi_hash_dev.py
- library/docs/development-pa-multi-hash-dev.md
