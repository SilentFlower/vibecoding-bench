# Engineering contract: PYTHON-MARKDOWN-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend fenced_code with closing_fence="exact" default and opt-in "at_least". At-least mode accepts a standalone closing fence of the same character at least as long as the opening run, keeps shorter runs inside code, rejects mixed-character/nonstandalone closers and supports backticks/tildes, language/attrs/highlight metadata and normal escaping. Scope regex/configuration per processor instance so one conversion cannot change later default output. Unknown mode rejects. Preserve all legacy exact-mode fixtures, including the intentional historical behavior, and avoid converting container/indentation semantics not included in this delivery.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_markdown_04_dev.py, and English compatibility documentation at library/docs/development-python-markdown-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/markdown/extensions/fenced_code.py
- library/tests/test_development_python_markdown_04_dev.py
- library/docs/development-python-markdown-04-dev.md
