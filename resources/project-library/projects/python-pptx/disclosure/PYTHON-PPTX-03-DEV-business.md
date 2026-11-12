# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add BaseShape.alternative_text/title backed by cNvPr descr/title for text boxes, pictures, groups and graphic frames through common nonvisual proxy. Exact str or None for absent, empty string explicit, None removes only own attribute, reject nonstrings before mutation. Preserve name/id, content/text, geometry, relationships and other unknown nonvisual data. Real PPTX save/reopen and XML escaping; decorative-extension flag is outside this precise alt/title delivery, no visual reader/rendering assertion.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_pptx_03_dev.py, and English compatibility documentation at library/docs/development-python-pptx-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pptx/shapes/base.py
- library/tests/test_development_python_pptx_03_dev.py
- library/docs/development-python-pptx-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
