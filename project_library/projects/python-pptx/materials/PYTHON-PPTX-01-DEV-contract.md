# Engineering contract: PYTHON-PPTX-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair RGBColor.from_string to accept exactly six ASCII hexadecimal characters, case-insensitive, otherwise clear ValueError including wrong type. Preserve legal channel values and six-character uppercase serialization; reject 5/7 length, whitespace, #/0x, Unicode digit lookalikes and nonhex. No CSS shorthand support or changes to RGBColor numeric constructor.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_pptx_01_dev.py, and English compatibility documentation at library/docs/development-python-pptx-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pptx/dml/color.py
- library/tests/test_development_python_pptx_01_dev.py
- library/docs/development-python-pptx-01-dev.md
