# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add sqlparse.sourcemap.SourceMap and immutable SourceSpan for opt-in original character offsets [start,end), one-based start/end line/column. Bind the actual candidate parse statements and all atomic/group tokens without changing default Token slots. Preserve every original character including whitespace/comments/CRLF, Unicode combining codepoints and multiple statement offsets; decoded bytes use explicit encoding and coordinates refer to decoded characters, not UTF-8 bytes or display graphemes. Exact source slicing must equal token/group text. Foreign tokens reject; any leaf value/type/identity/order mutation invalidates later lookups rather than silently reporting stale positions. Empty input is supported, and this tool never executes SQL.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlparse_03_dev.py, and English compatibility documentation at library/docs/development-sqlparse-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlparse/sourcemap.py
- library/tests/test_development_sqlparse_03_dev.py
- library/docs/development-sqlparse-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
