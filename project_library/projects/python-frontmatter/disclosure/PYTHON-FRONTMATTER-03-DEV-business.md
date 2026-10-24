# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Replace JSON-handler line-delimiter splitting with real JSON-object boundary recognition. Accept compact, empty, pretty and nested objects, escaped braces/quotes, non-ASCII metadata and a body that itself contains braces or JSON-looking lines. Consume exactly the first complete object and preserve the trailing body. Keep actual JSONHandler attachment, reserved business metadata, existing JSON serialization options and malformed-JSON exceptions. Non-object arbitrary prose remains ordinary content; no YAML/TOML behavior regression.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_frontmatter_03_dev.py, and English compatibility documentation at library/docs/development-python-frontmatter-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/frontmatter/default_handlers.py
- library/tests/test_development_python_frontmatter_03_dev.py
- library/docs/development-python-frontmatter-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
