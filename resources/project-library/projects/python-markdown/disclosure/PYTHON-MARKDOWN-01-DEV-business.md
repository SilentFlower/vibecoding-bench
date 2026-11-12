# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Extension configuration ownership: class-level or inherited config is a template, clone built-in dict/list/tuple/set/frozenset containers per instance before kwargs, and clone mutable values accepted by setConfig. Keep within-instance alias relationships, callback/opaque business-object identity, descriptions, existing bool/None parsing and unknown-key errors. Do not blindly deepcopy arbitrary callable objects; explicitly reject cyclic built-in configuration containers rather than recurse forever. Instance-level self.config built by existing extensions remains supported and ordinary Markdown output is unchanged. This is a complete extension lifecycle repair with real inherited/custom-extension checks.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_markdown_01_dev.py, and English compatibility documentation at library/docs/development-python-markdown-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/markdown/extensions/__init__.py
- library/tests/test_development_python_markdown_01_dev.py
- library/docs/development-python-markdown-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
