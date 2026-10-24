# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair LaTeXRenderer.render_raw_text text-mode escaping for literal backslash and tilde using a single pass that does not re-escape generated braces or control sequences. Preserve existing escapes for dollar, hash, braces, ampersand, underscore, percent and caret, Unicode text, and escape=False for code/math paths. Do not change URL/image escaping or claim TeX compilation.

Deliver real implementation, original-failing public tests at library/tests/test_development_mistletoe_06_dev.py, and English compatibility documentation at library/docs/development-mistletoe-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/mistletoe/latex_renderer.py
- library/tests/test_development_mistletoe_06_dev.py
- library/docs/development-mistletoe-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
