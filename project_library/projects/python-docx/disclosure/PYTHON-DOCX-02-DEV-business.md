# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair _set_element_datetime to convert aware datetime to UTC before writing existing Z format. Preserve the instant for positive/negative/nonhour offsets and day boundary; naive input keeps existing assumed-UTC wall value without querying host timezone. Apply created/modified/lastPrinted, retain existing whole-second precision and type validation. Prove actual docProps/core.xml and reopened values, no changes to legal reader behavior.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_docx_02_dev.py, and English compatibility documentation at library/docs/development-python-docx-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/docx/oxml/coreprops.py
- library/tests/test_development_python_docx_02_dev.py
- library/docs/development-python-docx-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
