# Engineering contract: MARKDOWNIFY-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix actual MarkdownConverter.convert_pre to choose a backtick fence of at least three characters and strictly longer than every consecutive backtick run in the converted code body. Preserve body content, existing strip_pre modes and language callback/fallback behavior. Validate the effective language as a string with no backtick, CR or LF, refusing structural info-line injection. Simple existing pre output must remain unchanged; demonstrate entire embedded fenced samples surviving as one outer code block, not only the presence of a helper.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdownify_o01_dev.py and concise English compatibility documentation at library/docs/development-markdownify-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdownify/__init__.py
- library/tests/test_development_markdownify_o01_dev.py
- library/docs/development-markdownify-o01-dev.md
