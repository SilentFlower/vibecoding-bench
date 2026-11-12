# Engineering contract: PYTHON-PPTX-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add TextFrame.text_direction str|None backed by bodyPr@vert with exactly pinned ST_TextVerticalType tokens. Support horizontal, vertical, vertical270, East Asian/Mongolian/WordArt modes as XML contracts; None removes direct attribute for inheritance, invalid input fails before mutation. Preserve text, shape rotation, margins/autofit/wrap and other bodyPr children/attrs. Real PPTX save/reopen proves metadata, not renderer glyph layout. Do not rotate shape to fake text direction.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_pptx_05_dev.py, and English compatibility documentation at library/docs/development-python-pptx-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pptx/text/text.py
- library/tests/test_development_python_pptx_05_dev.py
- library/docs/development-python-pptx-05-dev.md
