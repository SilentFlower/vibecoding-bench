# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement ftfy.atomic.fix_file_atomic(source,destination=None,*,encoding="utf-8",config=None,max_line_length=1000000) and frozen FileRepairResult(input_chars,output_chars,changed). Read strict explicit encoding in bounded chunks, reuse completed fix_chunks including whole-file HTML policy, write UTF8 to same-directory temp, flush/fsync and replace only on full success. Support in-place and separate output, preserve existing output permissions; decode/budget/source/write/replace errors leave old output unchanged and remove temps. Reject symlink/nonfile paths. Changed compares text, not source encoding bytes; no encoding guessing or whole-file buffering.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ft_atomic_file_dev.py and concise English compatibility documentation at library/docs/development-ft-atomic-file-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/ftfy/atomic.py
- library/development_tests/test_development_ft_atomic_file_dev.py
- library/docs/development-ft-atomic-file-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
