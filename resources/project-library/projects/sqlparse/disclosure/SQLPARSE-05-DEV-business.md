# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend existing Token.match(ttype,values,regex=False,case_sensitive=None) with explicit strict bool or None policy. None preserves all legacy behavior (keyword normalized case-insensitive, names sensitive, exact token-type match). True compares original value exactly; False uses Unicode casefold for ordinary string matching. Regex uses original value with Python re.IGNORECASE only when explicitly insensitive, without casefolding regex patterns or altering their escapes; partial-match semantics stay. Support values generators, None/type mismatch, quoted tokens as explicitly chosen text and preserve token.value/normalized without mutation. Do not misreport the already-working default Keyword case matching as a bug.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlparse_05_dev.py, and English compatibility documentation at library/docs/development-sqlparse-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlparse/sql.py
- library/tests/test_development_sqlparse_05_dev.py
- library/docs/development-sqlparse-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
