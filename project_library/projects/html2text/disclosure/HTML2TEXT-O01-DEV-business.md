# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add opt-in HTML2Text.adaptive_inline_code (default False), integrated into real code/kbd/tt tag/data handling. Buffer a single inline-code span, normalize line endings to spaces, choose a backtick delimiter strictly longer than any body run and apply CommonMark edge-backtick/double-ended-space padding so independent decoding restores the exact body. Ignore nested formatting markup while preserving its text/entities, handle multiple spans, empty spans and unclosed EOF without state leakage to later handle calls. Preserve default compatibility and pre paths. Do not merely escape source backticks or replace the entire document with a different converter.

Deliver meaningful original-failing public regression tests at library/test/test_development_html2text_o01_dev.py and concise English compatibility documentation at library/docs/development-html2text-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html2text/__init__.py
- library/test/test_development_html2text_o01_dev.py
- library/docs/development-html2text-o01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
