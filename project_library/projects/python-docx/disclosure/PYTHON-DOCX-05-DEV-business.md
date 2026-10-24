# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add _Row.repeat_header and allow_split_across_pages tri-state bool|None properties backed by correctly ordered trPr tblHeader/cantSplit OOXML declarations. None removes direct property/inherits, False remains explicit and cantSplit inverse is correct. Validate before mutation, preserve unrelated height/grid/merge/style settings, support nested/empty rows and roundtrip. Repeated-header placement remains caller responsibility (Word requires leading contiguous rows); do not claim pagination count/rendering enforcement.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_docx_05_dev.py, and English compatibility documentation at library/docs/development-python-docx-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/docx/table.py
- library/src/docx/oxml/table.py
- library/tests/test_development_python_docx_05_dev.py
- library/docs/development-python-docx-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
