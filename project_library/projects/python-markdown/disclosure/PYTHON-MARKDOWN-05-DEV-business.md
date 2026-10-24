# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add markdown.results.convert_document(text,extensions=(),extension_configs=None,**options) and frozen ConversionResult(html,toc,toc_tokens,metadata,references). Use a fresh real Markdown instance for each decoded-text call and capture actual extension-produced fields with deep copied result containers. Without extensions return explicit empty fields. Later documents or caller mutation of returned containers cannot change earlier/later result snapshots; opaque extension objects retain their normal documented lifecycle and are not falsely claimed clonable. Preserve existing markdown()/Markdown.convert APIs, registered extension behavior, output-format options and actual reference tuples. No invented source-position/diagnostic data or model calls.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_markdown_05_dev.py, and English compatibility documentation at library/docs/development-python-markdown-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/markdown/results.py
- library/tests/test_development_python_markdown_05_dev.py
- library/docs/development-python-markdown-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
