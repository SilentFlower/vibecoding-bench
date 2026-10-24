# Engineering contract: DATASET-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend actual ResultIter with context management and robust idempotent close. Early break, exhaustion, upstream fetch or row_type conversion failure must release result and dedicated streamed connection without closing shared Database. Detach owned resources before cleanup, attempt both even if cursor close fails, retain the first cleanup error for direct close, and preserve an existing business/conversion exception during cleanup. A closed iterator yields nothing; repeated close is safe. Test real SQLite streamed resources plus synthetic cleanup failures and existing empty/nonstreamed iteration behavior.

Deliver meaningful original-failing public regression tests at library/test/test_development_dataset_o04_dev.py and concise English compatibility documentation at library/docs/development-dataset-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dataset/util.py
- library/test/test_development_dataset_o04_dev.py
- library/docs/development-dataset-o04-dev.md
