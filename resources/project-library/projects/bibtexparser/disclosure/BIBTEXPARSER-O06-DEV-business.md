# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bibtexparser.diff.diff_libraries(before, after, *, ignore_fields=()). Compare real entries by exact citation key, case-normalized entry/field names and actual values independent of formatting/field order. Return stable ordered added/removed/changed records, distinguish missing fields from None, support explicit ignored fields, and separately report string-macro/comment/failed-block changes preserving multiplicity. Reports must own copied mutable values and never mutate or merge input Libraries; avoid repr-based unstable facts.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bibtexparser_o06_dev.py and concise English compatibility documentation at library/docs/development-bibtexparser-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bibtexparser/diff.py
- library/tests/test_development_bibtexparser_o06_dev.py
- library/docs/development-bibtexparser-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
