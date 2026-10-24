# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair tqdm.cli.posix_pipe to combine retained tail with each bounded read before delimiter scanning. Handle delimiters split at every byte position, multiple/consecutive delimiters, delimiter-at-EOF, incomplete delimiter suffix and undelimited final record. Forward every original byte exactly once, preserve byte-count mode for delim=b"", record-count mode and full-record callback mode used by numeric --update. Reject nonpositive/noninteger buffer size and nonbytes delimiter. Keep caller stream ownership/flush behavior; incomplete records may require record-sized carry memory, not falsely constant memory. Do not decode or execute input records in the generic pipe helper.

Deliver real implementation, original-failing public tests at library/tests/test_development_tqdm_02_dev.py, and English compatibility documentation at library/docs/development-tqdm-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/tqdm/cli.py
- library/tests/test_development_tqdm_02_dev.py
- library/docs/development-tqdm-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
