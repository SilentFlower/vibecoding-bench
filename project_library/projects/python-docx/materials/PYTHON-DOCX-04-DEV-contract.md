# Engineering contract: PYTHON-DOCX-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add Paragraph.add_hyperlink(text,address="",fragment="",style=None) and Hyperlink address/fragment/text setters plus remove(). Build real OOXML runs/relationships, support external URI and internal bookmark links without fetching addresses. Text replacement retains first-run formatting, removes extra text runs only; unchanged other paragraph content. Validate strings and nonempty target before adding side effects. Editing/removing drops an old relationship only according to its BEFORE-change reference count, retaining shared links and deduplicated targets. Save/reopen external URL/fragment/internal targets and formatting; no automatic bookmark creation or Word page rendering.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_docx_04_dev.py, and English compatibility documentation at library/docs/development-python-docx-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/docx/text/paragraph.py
- library/src/docx/text/hyperlink.py
- library/tests/test_development_python_docx_04_dev.py
- library/docs/development-python-docx-04-dev.md
