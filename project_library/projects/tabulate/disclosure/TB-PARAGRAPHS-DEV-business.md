# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix _wrap_text_to_colwidths so blank physical lines between, before and after text are retained as paragraph separators instead of filtered out. Respect existing splitlines terminal-newline convention, width wrapping, whitespace wrapping and numeric bypass behavior; apply consistently to data and headers. Do not broaden blank cells into missing values or change public signatures or upstream expectations unrelated to this bug. Add meaningful render and helper regressions.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_paragraphs_dev.py and concise English compatibility documentation at library/docs/development-tb-paragraphs-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tabulate/__init__.py
- library/development_tests/test_development_tb_paragraphs_dev.py
- library/docs/development-tb-paragraphs-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
