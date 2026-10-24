# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add --encoding-errors strict|replace|ignore to real CLI conversion while preserving its existing default ignore behavior and exact ordinary file output. Route the explicit policy through main/convert/convert_file and raw-buffer stdin where available, keeping existing direct calls valid with keyword-only errors="ignore" defaults. Explicit strict decoding exits nonzero before publishing that document and reports only input source plus byte position on stderr, without echoing content. Explicit replace/ignore follow standard codec semantics; valid Unicode output is unchanged and unknown policies are rejected. Do not treat strict decoding failures as successful truncated documents.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdown_it_o04_dev.py and concise English compatibility documentation at library/docs/development-markdown-it-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdown_it/cli/parse.py
- library/tests/test_development_markdown_it_o04_dev.py
- library/docs/development-markdown-it-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
