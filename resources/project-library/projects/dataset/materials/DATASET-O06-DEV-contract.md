# Engineering contract: DATASET-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add keyword-only on_error="flush"|"discard" to actual ChunkedInsert/ChunkedUpdate and validate positive non-bool chunksize. Default flush preserves existing behavior. In discard mode normal exit still flushes, while an application exception clears only the pending queue (and pending insert field set), invokes no callback/write and preserves the original exception; already committed chunks remain. Empty flush is an idempotent no-op. Preserve callback/write failures as failures and explicit outer Database transaction rollback behavior. Demonstrate real SQLite insert/update, pending state reuse and full-chunk vs tail distinction; never claim discard undoes committed chunks.

Deliver meaningful original-failing public regression tests at library/test/test_development_dataset_o06_dev.py and concise English compatibility documentation at library/docs/development-dataset-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dataset/chunked.py
- library/test/test_development_dataset_o06_dev.py
- library/docs/development-dataset-o06-dev.md
