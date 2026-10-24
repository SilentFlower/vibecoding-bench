# Engineering contract: CK-STABLE-WRITE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement click.writing.write_if_changed(path,content,*,encoding="utf-8") returning whether actual write occurred. Compare final encoded bytes first; identical bytes preserve inode/mtime/mode exactly. Changed/new data is serialized before I/O, written to same-directory temporary, flushed/fsynced, mode preserved (0600 when new) then atomically replaced, with cleanup on failure. Support bytes and encoded text; reject invalid content and symlinks. Verify real CliRunner invocation; do not alter open_file defaults or promise compare-and-swap locking/parent-directory fsync durability.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ck_stable_write_dev.py and concise English compatibility documentation at library/docs/development-ck-stable-write-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/click/writing.py
- library/development_tests/test_development_ck_stable_write_dev.py
- library/docs/development-ck-stable-write-dev.md
