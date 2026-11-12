# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add sqlparse.fingerprint.fingerprint(text,encoding=None,digest=False,replace_constants=True) using real candidate lexer token types. Remove actual comments/whitespace, normalize keyword spelling/spacing and replace numeric/single-quoted/dollar-quoted literals with ?, optionally also NULL/TRUE/FALSE. Preserve identifiers including quoted names, operators, statement boundaries, existing named/positional placeholders and IN-list cardinality. Return deterministic canonical text or SHA256 of it. Do not treat comment markers inside strings as comments, do not connect to databases, and explicitly state this groups token shape rather than proving semantic equivalence or generating safe executable parameterized SQL.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlparse_04_dev.py, and English compatibility documentation at library/docs/development-sqlparse-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlparse/fingerprint.py
- library/tests/test_development_sqlparse_04_dev.py
- library/docs/development-sqlparse-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
