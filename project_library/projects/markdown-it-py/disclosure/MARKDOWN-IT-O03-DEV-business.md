# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add immutable HighlightResult(html: str, block: bool=False) and integrate it into actual RendererHTML.fence. A nonempty explicit block result is returned as its complete trusted container with exactly one existing/added terminal newline, even when it starts with div/section rather than pre. Explicit inline HTML is wrapped by the real pre/code renderer including language attrs, without legacy pre-prefix inference. Empty explicit results fall back to escaped source. Preserve old string callbacks/pre heuristic and callback arguments, reject invalid result field/types and propagate callback failures. This is trusted highlighter output, not an HTML sanitizer.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdown_it_o03_dev.py and concise English compatibility documentation at library/docs/development-markdown-it-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdown_it/renderer.py
- library/tests/test_development_markdown_it_o03_dev.py
- library/docs/development-markdown-it-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
