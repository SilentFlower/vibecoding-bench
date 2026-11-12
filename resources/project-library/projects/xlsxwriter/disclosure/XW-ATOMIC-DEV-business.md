# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement xlsxwriter.atomic.atomic_workbook(destination,options=None) yielding a real Workbook writing to a same-directory temporary file. Only after body success and successful close/fsync replace the destination atomically; retain existing regular file permissions. Body/close/replace failures must preserve old destination and clean temporary files without masking original errors. Reject symlink/nonfile destinations, support new files and ordinary Workbook options without mutating caller mappings. This is a single local file operation, not a multi-file or hostile-race transaction.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xw_atomic_dev.py and concise English compatibility documentation at library/docs/development-xw-atomic-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xlsxwriter/atomic.py
- library/development_tests/test_development_xw_atomic_dev.py
- library/docs/development-xw-atomic-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
