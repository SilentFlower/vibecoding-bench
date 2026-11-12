# Engineering contract: TD-ATOMIC-STORAGE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tinydb.atomic.AtomicJSONStorage(Storage) with TinyDB-compatible read/write/close and constructor (path, *, create_dirs=False, encoding="utf-8", **json_options). Serialize completely before opening a same-directory temporary file, flush/fsync and atomically os.replace; preserve existing mode, use 0600 for new files, clean temporary files and retain old bytes on serialization/write/replace failure. Read current path each time, return None for absent/empty files, reject nonmapping JSON roots and symlink targets, and reject reads/writes after close. Verify reopen and shrinking data. Preserve existing JSONStorage and do not claim cross-process locking, hostile-directory race protection or parent-directory crash durability.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_td_atomic_storage_dev.py and concise English compatibility documentation at library/docs/development-td-atomic-storage-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tinydb/atomic.py
- library/development_tests/test_development_td_atomic_storage_dev.py
- library/docs/development-td-atomic-storage-dev.md
