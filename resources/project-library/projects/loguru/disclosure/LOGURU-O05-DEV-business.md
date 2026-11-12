# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Introduce string-compatible RecordName for non-None actual caller module names and explicit format spec short:N (positive decimal count of full trailing segments), optionally followed by | and a normal string format spec. Abbreviate preceding dotted segments to first Unicode characters, preserving empty segments, full stored value, JSON, pickle and all old standard str formats including numeric width. Integrate real Logger formatting, preserve None caller metadata unchanged, reject invalid new specs and avoid adding a replacement truncated record field or silently redefining {name:2}.

Deliver meaningful original-failing public regression tests at library/tests/test_development_loguru_o05_dev.py and concise English compatibility documentation at library/docs/development-loguru-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/loguru/_logger.py
- library/loguru/_recattrs.py
- library/tests/test_development_loguru_o05_dev.py
- library/docs/development-loguru-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
