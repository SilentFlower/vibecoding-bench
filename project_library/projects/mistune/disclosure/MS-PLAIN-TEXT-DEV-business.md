# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement mistune.renderers.text.PlainTextRenderer(include_urls=False) as BaseRenderer with NAME="text". Retain inline text/entity semantics and literal code, paragraph/heading/quote boundaries, ordered/unordered list item separation, task state, table cell boundaries and footnote references from actual tokens. Strip raw HTML tags while keeping text; optionally append link/image URLs without duplicating identical visible URLs. Handle AST plugin containers through children, empty input and repeated use without state leakage. Output must not include formatting HTML or silently use the HTML renderer and remove all structure.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ms_plain_text_dev.py and concise English compatibility documentation at library/docs/development-ms-plain-text-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/mistune/renderers/text.py
- library/development_tests/test_development_ms_plain_text_dev.py
- library/docs/development-ms-plain-text-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
