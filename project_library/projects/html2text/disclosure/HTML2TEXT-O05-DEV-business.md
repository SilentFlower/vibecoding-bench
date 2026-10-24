# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add visible_content=False and a per-handle hidden_regions count integrated before actual tag/data side effects. In opt-in mode omit entire template or HTML hidden-attribute subtrees (attribute presence including hidden="false"), including nested formatting/resources; handle void hidden elements without hiding following siblings and recover matching ancestor closes without corrupting existing quiet/head/style/script accounting. Unclosed hidden EOF hides the remainder of only that document and state resets before reuse. Default text remains unchanged, do not infer CSS/script visibility or claim sanitization; counts report top-level omitted regions.

Deliver meaningful original-failing public regression tests at library/test/test_development_html2text_o05_dev.py and concise English compatibility documentation at library/docs/development-html2text-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html2text/__init__.py
- library/test/test_development_html2text_o05_dev.py
- library/docs/development-html2text-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
