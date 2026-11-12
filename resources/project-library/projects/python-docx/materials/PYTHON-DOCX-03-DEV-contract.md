# Engineering contract: PYTHON-DOCX-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Validate Document.add_comment supplied Run or nonempty Run iterable BEFORE creating comments/relationships/markers. Every provided Run belongs to current main document part and XML tree; reject foreign/header/footer/detached/unsupported textbox story, reverse/duplicate/non-Run/empty ranges. Preserve single Run and ordered cross-paragraph first/last range semantics (unprovided intervening runs naturally included), author/initials. Failures leave both documents and comments part absent/unmodified, no only-after-allocation check.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_docx_03_dev.py, and English compatibility documentation at library/docs/development-python-docx-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/docx/document.py
- library/tests/test_development_python_docx_03_dev.py
- library/docs/development-python-docx-03-dev.md
