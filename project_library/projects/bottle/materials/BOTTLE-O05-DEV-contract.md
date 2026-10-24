# Engineering contract: BOTTLE-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add FileUpload.save_atomic(destination, *, overwrite=False, chunk_size=65536) for real path/directory targets. Complete copying in a private same-directory temporary file before publication; overwrite=True atomically replaces, False uses exclusive publication that cannot overwrite a competitor. Restore original input cursor on success and read/write/replace failures, preserve existing destination bytes on failures, clean only owned temporary files and validate positive chunk sizes. Leave existing save/stream behavior unchanged and do not claim crash durability.

Deliver meaningful original-failing public regression tests at library/test/test_development_bottle_o05_dev.py and concise English compatibility documentation at library/docs/development-bottle-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bottle.py
- library/test/test_development_bottle_o05_dev.py
- library/docs/development-bottle-o05-dev.md
