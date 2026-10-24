# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Token.deep_copy() for actual token graphs, isolating nested children/image-alt tokens, attrs, map and supported arbitrary meta while preserving shared aliases and cycles within the copied graph. Original Token.copy(**changes) remains shallow. Standard deepcopy-compatible custom values participate normally; uncopyable opaque meta raises its original failure and must never be silently shared or partially mutate the original. Demonstrate independent rendered document edits and self-referential metadata, not serialization that drops types or cycle relationships.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdown_it_o05_dev.py and concise English compatibility documentation at library/docs/development-markdown-it-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdown_it/token.py
- library/tests/test_development_markdown_it_o05_dev.py
- library/docs/development-markdown-it-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
