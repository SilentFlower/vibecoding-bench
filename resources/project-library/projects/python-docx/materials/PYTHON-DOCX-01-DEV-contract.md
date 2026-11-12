# Engineering contract: PYTHON-DOCX-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair CT_CoreProperties._datetime_of_element for existing date element with None/empty/whitespace text: return None like a missing/invalid date, without broad exception swallowing. Cover created/modified/lastPrinted through a real saved/reopened DOCX. Keep legal W3CDTF year/date/time/offset parsing and existing invalid-string policy unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_docx_01_dev.py, and English compatibility documentation at library/docs/development-python-docx-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/docx/oxml/coreprops.py
- library/tests/test_development_python_docx_01_dev.py
- library/docs/development-python-docx-01-dev.md
