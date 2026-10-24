# Engineering contract: RICH-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Rich cells/Text wrapping as one complete width-boundary delivery: use the same split_graphemes widths for ZWJ/VS special paths, guard zero total grapheme width and positions beyond the end before offset estimation, and honor the selected Unicode table. set_cell_size/chop_cells/Text.wrap at <=0 width consistently return empty text/list/Lines, while split_text at <=0 returns empty-left/original-right for ASCII and Unicode. Preserve positive-width ASCII fast paths, grapheme boundaries, normal padding, replacement spaces for splitting a double-width glyph, existing Panel layout and all original tests. Never turn all Unicode characters into width two or claim full UAX grapheme conformance beyond the pinned model.

Deliver real implementation, original-failing public tests at library/tests/test_development_rich_01_dev.py, and English compatibility documentation at library/docs/development-rich-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/rich/cells.py
- library/rich/text.py
- library/tests/test_development_rich_01_dev.py
- library/docs/development-rich-01-dev.md
