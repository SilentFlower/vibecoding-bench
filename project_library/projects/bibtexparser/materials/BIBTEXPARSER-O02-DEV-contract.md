# Engineering contract: BIBTEXPARSER-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bibtexparser.validation.validate_entries(library, *, rules=None, version="bibtex-v1"). Supply explicit article/book rules, required fields and alternative author/editor groups; treat empty/None as absent and allow custom required/one_of/allowed rules. Return ordered structured diagnostics with key, field, stable code and real available source line. Unknown types/fields must be reported without deleting data. Preserve original Library and permissive parser behavior; reject unsupported rule versions.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bibtexparser_o02_dev.py and concise English compatibility documentation at library/docs/development-bibtexparser-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bibtexparser/validation.py
- library/tests/test_development_bibtexparser_o02_dev.py
- library/docs/development-bibtexparser-o02-dev.md
