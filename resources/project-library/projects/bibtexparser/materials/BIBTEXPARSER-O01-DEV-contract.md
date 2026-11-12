# Engineering contract: BIBTEXPARSER-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bibtexparser.crossref.ResolveCrossrefMiddleware(missing="error") as a non-mutating LibraryMiddleware. Resolve nested case-sensitive crossref dependencies, inherit only missing fields, map parent title to booktitle for inproceedings/incollection and preserve explicit child values including empty strings. Record inherited field sources in parser metadata, reject cycles and failed/duplicate blocks, and allow explicit missing="ignore". Keep the default parse stack unchanged and preserve source object isolation.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bibtexparser_o01_dev.py and concise English compatibility documentation at library/docs/development-bibtexparser-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bibtexparser/crossref.py
- library/tests/test_development_bibtexparser_o01_dev.py
- library/docs/development-bibtexparser-o01-dev.md
