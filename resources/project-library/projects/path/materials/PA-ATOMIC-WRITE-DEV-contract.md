# Engineering contract: PA-ATOMIC-WRITE-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Path.atomic_write(content,*,encoding="utf-8",if_changed=False). Validate and encode str/bytes before creating a same-directory temp, flush/fsync, retain old mode or use 0600 when new, replace atomically and clean failure paths. Reject symlinks; if_changed=True preserves inode/mtime/mode when bytes match and returns False, otherwise True. Serialization/replace failures preserve old bytes. Keep ordinary write methods unchanged and do not promise concurrent compare-and-swap or directory-fsync crash guarantees.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_pa_atomic_write_dev.py and concise English compatibility documentation at library/docs/development-pa-atomic-write-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/path/__init__.py
- library/development_tests/test_development_pa_atomic_write_dev.py
- library/docs/development-pa-atomic-write-dev.md
