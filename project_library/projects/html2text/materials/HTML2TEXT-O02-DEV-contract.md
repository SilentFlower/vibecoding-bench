# Engineering contract: HTML2TEXT-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add table_caption_mode="legacy"|"paragraph" to real HTML2Text table conversion, defaulting to compatibility. Paragraph mode separates each nonempty caption from surrounding content and the actual table header/data while preserving existing inline emphasis/link conversion, repeated/empty captions and normal header separator generation. Keep bypass_tables/ignore_tables semantics with readable captions, ordinary caption-free tables and default output unchanged; reject unknown strategy when a caption is encountered. Do not duplicate caption text, rewrite the header as a title or alter original regression fixtures.

Deliver meaningful original-failing public regression tests at library/test/test_development_html2text_o02_dev.py and concise English compatibility documentation at library/docs/development-html2text-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html2text/__init__.py
- library/test/test_development_html2text_o02_dev.py
- library/docs/development-html2text-o02-dev.md
