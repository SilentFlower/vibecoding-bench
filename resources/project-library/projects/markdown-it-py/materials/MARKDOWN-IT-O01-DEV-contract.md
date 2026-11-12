# Engineering contract: MARKDOWN-IT-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix actual MarkdownIt.reset_rules to restore the entering active-rule sets across core, block, inline and inline2 in a finally block, on normal return, exceptions and BaseException cancellation. Nested contexts restore their own entering state, including initially disabled rules, and original exceptions propagate unchanged. Verify actual rendering after failure. Do not promise rollback of newly registered/replaced rule functions, replace parser objects or suppress consumer failures.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdown_it_o01_dev.py and concise English compatibility documentation at library/docs/development-markdown-it-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdown_it/main.py
- library/tests/test_development_markdown_it_o01_dev.py
- library/docs/development-markdown-it-o01-dev.md
