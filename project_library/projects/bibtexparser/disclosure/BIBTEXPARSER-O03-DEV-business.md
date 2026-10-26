# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bibtexparser.pages.NormalizePages as an opt-in non-mutating BlockMiddleware. Normalize complete ascending numeric page ranges separated by commas from hyphen/en-dash/em-dash to BibTeX double hyphens, preserving digit text and first original_pages metadata. Leave electronic/single/Roman/decimal/descending or mixed unknown formats wholly unchanged. Modify only pages, preserve other fields and default stacks, and remain idempotent.

Leading and trailing whitespace around a recognized pages value may be preserved or stripped. Digit text, normalized range separators and the first original_pages metadata must still be preserved.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bibtexparser_o03_dev.py and concise English compatibility documentation at library/docs/development-bibtexparser-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bibtexparser/pages.py
- library/tests/test_development_bibtexparser_o03_dev.py
- library/docs/development-bibtexparser-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
