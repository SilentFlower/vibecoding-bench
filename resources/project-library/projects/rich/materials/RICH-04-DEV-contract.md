# Engineering contract: RICH-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Rich ANSI decoding by removing only the designated ignorable C0 characters already stripped from plain Text (NUL..BS, VT/FF, SO..SUB, FS..US) before recognizing escape sequences; preserve TAB/LF/CR handling. SGR sequences with such bytes after ESC or within parameters decode into actual styles. Unrecognized/truncated sequences never leave a raw ESC in emitted plain fragments; unsupported suffix text may remain literal. Preserve standard SGR/OSC8-ST links, colors and decoder style state. Document this limited parser policy rather than claim a complete arbitrary terminal-protocol sanitizer; do not reinterpret or execute terminal controls beyond existing supported sequences.

Deliver real implementation, original-failing public tests at library/tests/test_development_rich_04_dev.py, and English compatibility documentation at library/docs/development-rich-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/rich/ansi.py
- library/tests/test_development_rich_04_dev.py
- library/docs/development-rich-04-dev.md
