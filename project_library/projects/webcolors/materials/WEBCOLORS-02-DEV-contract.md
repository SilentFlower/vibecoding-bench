# Engineering contract: WEBCOLORS-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Fix html5_parse_legacy_color to strip only ASCII space, TAB, LF, FF and CR, leaving NBSP, vertical tab and other Unicode whitespace for the existing legacy replacement/padding algorithm. Preserve named colors, short hex, BMP/non-BMP handling, 128-character truncation, transparent rejection and the separate strict HTML simple-color contract. NBSP-red-NBSP must produce (0,237,0), not silently become red. Whitespace-only input follows the existing legacy padding path. This is a real parser repair, not a generic trim helper.

Deliver real implementation, original-failing public tests at library/tests/test_development_webcolors_02_dev.py, and English compatibility documentation at library/docs/development-webcolors-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/webcolors/_html5.py
- library/tests/test_development_webcolors_02_dev.py
- library/docs/development-webcolors-02-dev.md
