# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Path.iter_lines(encoding=None,errors="strict",*,retain=True,newline=None), a lazy text iterator owning one context-managed stream. None uses universal newline normalization; "" retains original CR/LF/CRLF terminators; retain=False removes exactly the physical line ending. Preserve blank lines, Unicode, missing final newline and codec error policy. Early generator.close and decode/I/O exceptions must close the stream, with no whole-file read or changes to existing lines/read_text behavior.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_pa_iter_lines_dev.py and concise English compatibility documentation at library/docs/development-pa-iter-lines-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/path/__init__.py
- library/development_tests/test_development_pa_iter_lines_dev.py
- library/docs/development-pa-iter-lines-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
