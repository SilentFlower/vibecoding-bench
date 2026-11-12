# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tomlkit.editing.apply_edits(document,operations), materializing a finite ordered sequence of set/delete/test records on a detached deep copy. Paths are nonempty sequences of literal string keys and nonnegative integer array indices, never dotted-string parsing. Set may explicitly create missing mapping parents, not arrays; array indices must exist. Test compares unwrapped value and exact Python type before continuing. A late invalid operation, path error or failed test must leave original text and objects unchanged. Preserve unaffected formatting/comments, serialize and reparse final candidate. Do not modify parser internals or promise file-system transactions.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tk_edits_dev.py and concise English compatibility documentation at library/docs/development-tk-edits-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tomlkit/editing.py
- library/development_tests/test_development_tk_edits_dev.py
- library/docs/development-tk-edits-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
