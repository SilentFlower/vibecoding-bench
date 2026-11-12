# Engineering contract: PYTHON-MARKDOWN-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add opt-in markdown.extensions.uri_autolink with UriAutolinkExtension(schemes=(http,https,ssh,urn)). Match complete angle-bracket URI syntax before raw-HTML handling but after code/escapes, use per-instance case-insensitive validated scheme allowlists, and build ElementTree anchor attributes/AtomicString text through the real serializer. Forbid javascript/vbscript/data even if requested; unsupported schemes do not become links, ordinary HTML/email/standard autolinks keep existing semantics, and code spans/blocks never expand. No global lexer mutation or network access. Clearly state this policy controls new autolinks only and does not sanitize Markdown raw HTML as a whole.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_markdown_03_dev.py, and English compatibility documentation at library/docs/development-python-markdown-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/markdown/extensions/uri_autolink.py
- library/tests/test_development_python_markdown_03_dev.py
- library/docs/development-python-markdown-03-dev.md
