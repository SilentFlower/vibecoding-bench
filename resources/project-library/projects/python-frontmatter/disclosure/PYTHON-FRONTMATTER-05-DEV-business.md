# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair load() for standard binary streams by decoding before format detection, using the requested encoding from the current cursor. Extend dump() to io.BufferedIOBase/io.RawIOBase including BytesIO and real wb files, encoding exactly once; text streams receive str and paths retain their existing explicit encoding behavior. Do not catch TypeError to retry writes; do not rewind, truncate or close caller-owned streams. Decode/encode/write errors propagate. Roundtrip leading-blank TOML, compact JSON and reserved business metadata from prior deliveries without losing the handler or Unicode content.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_frontmatter_05_dev.py, and English compatibility documentation at library/docs/development-python-frontmatter-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/frontmatter/__init__.py
- library/tests/test_development_python_frontmatter_05_dev.py
- library/docs/development-python-frontmatter-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
