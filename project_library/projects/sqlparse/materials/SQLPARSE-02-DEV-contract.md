# Engineering contract: SQLPARSE-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair both comma_first and compact CLI options as one boolean parsing family. Preserve explicit True/False compatibility with case-insensitive true/false/1/0 only, support bare option as true and --no-comma-first/--no-compact as false, define repeated options as last-wins and reject empty/unknown literals with argparse usage error. Defaults remain false and Python formatter API semantics unchanged. Verify actual formatted output, not only argparse fields, and document that a filename should precede an optional-value boolean or follow -- to avoid optional argument ambiguity.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlparse_02_dev.py, and English compatibility documentation at library/docs/development-sqlparse-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlparse/cli.py
- library/tests/test_development_sqlparse_02_dev.py
- library/docs/development-sqlparse-02-dev.md
