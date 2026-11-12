# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bibtexparser.identifiers.NormalizeIdentifiers(fields=("doi", "isbn"), strict=False) as an opt-in non-mutating BlockMiddleware. Canonicalize DOI URL/doi prefixes and case without stripping potentially valid punctuation, normalize ISBN10/13 whitespace/hyphens and verify check digits including X. Preserve original values/status in metadata; invalid values remain unchanged unless strict requests failure. Only selected fields change, no external lookup or guessed repairs, and normal parsing/writing remains compatible.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bibtexparser_o05_dev.py and concise English compatibility documentation at library/docs/development-bibtexparser-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bibtexparser/identifiers.py
- library/tests/test_development_bibtexparser_o05_dev.py
- library/docs/development-bibtexparser-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
