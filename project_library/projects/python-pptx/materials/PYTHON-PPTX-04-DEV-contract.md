# Engineering contract: PYTHON-PPTX-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add _Paragraph.bullet read and set_bullet(kind,character="•",scheme="arabicPeriod",start=1). kind character/number/none or None inheritance; single character, number scheme from pinned ST_TextAutonumberScheme and strict 1..32767 start. Validate before mutation; replace mutually exclusive buNone/buChar/buAutoNum/buBlip only, insert before tabLst/defRPr/extLst per XSD. Preserve text, level, font and other paragraph properties, read unsupported image bullet as unsupported without implicit mutation. Real saved/reopened OOXML, never prefix fake numbering text.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_pptx_04_dev.py, and English compatibility documentation at library/docs/development-python-pptx-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pptx/text/text.py
- library/tests/test_development_python_pptx_04_dev.py
- library/docs/development-python-pptx-04-dev.md
