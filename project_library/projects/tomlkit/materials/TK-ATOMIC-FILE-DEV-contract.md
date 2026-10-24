# Engineering contract: TK-ATOMIC-FILE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tomlkit.files.load_with_digest(path) returning (UTF8 parsed_document,raw_bytes_sha256), and atomic_save(document,path,*,expected_digest=None) returning the new digest. Validate serialized TOML before I/O, check optional original digest before temp creation and before replacement, reject stale files with StaleDocumentError, preserve mode or choose 0600 for new files, flush/fsync a same-directory temporary then os.replace and clean failures. Reject symlinks and preserve old bytes on validation, staleness or replacement failure. Do not claim cross-process compare-and-swap locking or directory-fsync crash durability; ordinary parse/dump APIs stay unchanged.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tk_atomic_file_dev.py and concise English compatibility documentation at library/docs/development-tk-atomic-file-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tomlkit/files.py
- library/development_tests/test_development_tk_atomic_file_dev.py
- library/docs/development-tk-atomic-file-dev.md
