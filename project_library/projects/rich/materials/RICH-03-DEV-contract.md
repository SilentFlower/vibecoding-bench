# Engineering contract: RICH-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Text integer indexing: normalize a negative offset exactly once against codepoint length, enforce normal IndexError at both bounds and transfer base style plus every overlapping span to the one-character result. Positive and corresponding negative indexes are semantically identical; preserve source Text untouched, Unicode codepoint indexing, empty behavior, end="" on the selected character and existing slice rules. Do not clamp too-negative indexes to zero or turn indexing into grapheme segmentation. This is a complete styled-selection repair with real overlapping style checks.

Deliver real implementation, original-failing public tests at library/tests/test_development_rich_03_dev.py, and English compatibility documentation at library/docs/development-rich-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/rich/text.py
- library/tests/test_development_rich_03_dev.py
- library/docs/development-rich-03-dev.md
