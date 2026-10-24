# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add InlineShape.alternative_text and title backed by wp:docPr descr/title. Expose exact str or None when absent, empty str is explicit metadata, None removes only own attribute, reject nonstring before mutation. Preserve drawing ID/name, relationship, shape dimensions, image bytes and unrelated/unknown attributes. Real local PNG to saved/reopened DOCX proves independent metadata and XML escaping; no visual rendering claims, network or generated image dependency.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_docx_06_dev.py, and English compatibility documentation at library/docs/development-python-docx-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/docx/shape.py
- library/tests/test_development_python_docx_06_dev.py
- library/docs/development-python-docx-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
