# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair rows_from_file automatic CSV dialect detection to consider explicit common delimiters comma/tab/semicolon/pipe, not arbitrary repeated letters in URLs or names. If sniffing fails and no candidate delimiter appears, treat as single CSV column with normal header/rows; preserve Unicode, header-only and ordinary multi-column files. Existing explicit format/dialect and CLI explicit --sniff semantics remain unchanged. If candidate separators are present but inconsistent, do not silently downgrade malformed multicolumn data. Real row dicts must match input, not only format labels.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlite_utils_03_dev.py, and English compatibility documentation at library/docs/development-sqlite-utils-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlite_utils/utils.py
- library/tests/test_development_sqlite_utils_03_dev.py
- library/docs/development-sqlite-utils-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
