# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add registered segmented-list RST directive with required pipe-CSV columns option, optional inline-formatted title, class/name and pipe-CSV content rows. Parse through real Directive/state.inline_text into table/tgroup/colspec/thead/tbody/row/entry nodes and actual HTML writer output. Preserve quoted pipes, empty cells, Unicode/inline markup and ordinary non-directive colon paragraphs. Reject absent/empty headings, malformed CSV or inconsistent row widths with real directive diagnostics and no half table. Do not implement as raw HTML/text substitution or change existing table/list-table syntax.

Deliver meaningful original-failing public regression tests at library/tests/test_development_docutils_o02_dev.py and concise English compatibility documentation at library/docs/development-docutils-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/docutils/docutils/parsers/rst/directives/segmented.py
- library/docutils/docutils/parsers/rst/directives/__init__.py
- library/docutils/docutils/parsers/rst/languages/en.py
- library/tests/test_development_docutils_o02_dev.py
- library/docs/development-docutils-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
