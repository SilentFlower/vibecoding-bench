# Engineering contract: PYTHON-FRONTMATTER-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add frontmatter.parsing ParseResult/ParseError/parse_result(text, encoding="utf-8", handler=None, defaults=None, strict=False). Results expose status (absent/present/malformed/non_mapping), independent metadata, stripped content, actual handler and error. Explicitly distinguish malformed/split failure and non-mapping roots from absent metadata; empty/null YAML is a valid empty mapping. Strict mode raises ParseError carrying the same result for malformed/non_mapping only. Preserve legacy parse/loads behavior and custom-handler authority. Compact/nested JSON introduced by the earlier delivery must work through the new result API. Decode errors remain real decode errors, never absent status.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_frontmatter_04_dev.py, and English compatibility documentation at library/docs/development-python-frontmatter-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/frontmatter/parsing.py
- library/tests/test_development_python_frontmatter_04_dev.py
- library/docs/development-python-frontmatter-04-dev.md
