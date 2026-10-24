# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement dotenv.editing.update_keys(path, updates, *, remove=(), encoding="utf-8", follow_symlinks=False). Validate and serialize the complete mapping/removal list before opening rewrite; reject malformed keys, NUL/nonstring values and conflicting update/delete keys. Reuse rewrite for one atomic replacement, preserve every non-target parsed record and newline byte, update first target occurrence and remove duplicate target definitions, remove all requested-key occurrences, append missing updates in mapping order with a needed separator, and return (updated_keys_tuple, removed_keys_tuple). Single-quote escaping must roundtrip backslashes, quotes and multiline values. Preserve mode, symlink option and failure cleanup.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_de_batch_dev.py and concise English compatibility documentation at library/docs/development-de-batch-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/dotenv/editing.py
- library/development_tests/test_development_de_batch_dev.py
- library/docs/development-de-batch-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
