# Engineering contract: PYTHON-FRONTMATTER-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair format detection across checks/check/load/loads/parse: the same leading whitespace and CRLF normalization already accepted by parse must not lose the actual YAML/TOML handler when building a Post. Preserve explicit handler identity, body trimming, reserved business metadata and default no-frontmatter behavior. Roundtripping a leading-blank TOML document must remain TOML, not silently switch to YAML. Do not broaden this delivery to BOM guessing or arbitrary body delimiter search.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_frontmatter_02_dev.py, and English compatibility documentation at library/docs/development-python-frontmatter-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/frontmatter/__init__.py
- library/tests/test_development_python_frontmatter_02_dev.py
- library/docs/development-python-frontmatter-02-dev.md
