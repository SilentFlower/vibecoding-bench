# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Build charset_normalizer.atomic.normalize_file_atomic on the delivered strict transcode API. Bound source reads, detect actual text, complete target encoding before touching destination and atomically publish a same-directory temporary file. Default in-place or explicit separate output, preserve existing target mode/new-file private mode, reject symlink paths and clean only owned temporary files on encoding/write/replace failures. Source and old target bytes must survive failures; report actual written bytes/loss count, keep default APIs read-only and do not claim directory crash durability.

Deliver meaningful original-failing public regression tests at library/tests/test_development_charset_normalizer_o06_dev.py and concise English compatibility documentation at library/docs/development-charset-normalizer-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/charset_normalizer/atomic.py
- library/tests/test_development_charset_normalizer_o06_dev.py
- library/docs/development-charset-normalizer-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
