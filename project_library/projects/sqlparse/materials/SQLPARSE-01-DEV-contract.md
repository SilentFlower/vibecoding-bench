# Engineering contract: SQLPARSE-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair actual sqlparse CLI file lifecycle: read input, validate formatter options and complete formatting/encoding before touching any output destination. For --in-place and explicit outfile use same-directory temporary bytes, flush/fsync and os.replace, preserve existing mode/owner and clean temporary files on pre-replace failure. Reject symlink/nonregular output. Invalid options, formatting exceptions, encoding and IO failures return nonzero without truncating old bytes; stdout remains caller-owned and stdin in-place stays forbidden. Continue other explicit files after one fails using current aggregate status. Preserve successful output text, ordinary parser flags, input encoding and existing diagnostic prefixes. Never execute SQL or contact a database.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlparse_01_dev.py, and English compatibility documentation at library/docs/development-sqlparse-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlparse/cli.py
- library/tests/test_development_sqlparse_01_dev.py
- library/docs/development-sqlparse-01-dev.md
