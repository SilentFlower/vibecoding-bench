# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add public fragments.extract_section(document,section_id,*,external="error"|"include_notes") selecting one exact real section id into a new document, preserving source/line, nested structure and internal refid/name maps without modifying the old tree. Selected section becomes top level structurally; actual HTML publication must work. Default rejects references outside selection. include_notes appends only referenced external footnote/citation closure and filters backrefs to included ids; external section/unknown targets still error rather than silently including arbitrary chapters. Missing/duplicate IDs and invalid policies fail explicitly. Do not slice rendered HTML, guess titles, fake URLs or claim unimplemented CLI support.

Deliver meaningful original-failing public regression tests at library/tests/test_development_docutils_o06_dev.py and concise English compatibility documentation at library/docs/development-docutils-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/docutils/docutils/fragments.py
- library/tests/test_development_docutils_o06_dev.py
- library/docs/development-docutils-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
