# Engineering contract: DOCUTILS-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix docutils.__main__.main ImportError handling so missing reader/parser/writer reports failure on stderr, exits nonzero and emits no stdout document/help hint or target artifact. Preserve explicit --traceback reraising with stack and normal successful HTML publication/exit. Do not swallow failures as success, change valid component selection or broadly catch arbitrary developer exceptions. Demonstrate actual python -m docutils subprocess behavior with isolated config.

Deliver meaningful original-failing public regression tests at library/tests/test_development_docutils_o01_dev.py and concise English compatibility documentation at library/docs/development-docutils-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/docutils/docutils/__main__.py
- library/tests/test_development_docutils_o01_dev.py
- library/docs/development-docutils-o01-dev.md
