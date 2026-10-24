# Engineering contract: DOCUTILS-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend CodeBlock with caption option, using the original tag_code language/highlight/number-lines path and wrapping captioned output in an actual code-figure figure whose first child is literal_block and second is inline-parsed caption. Attach name/id to the figure for real references and preserve source/line; HTML5 naturally emits figure/figcaption and code escaping. Caption-free nodes/output remain unchanged. Reject empty captions through directive option validation and preserve Unicode/multiline title text and original lexer error policy; do not replace code contents with raw HTML or a rubric.

Deliver meaningful original-failing public regression tests at library/tests/test_development_docutils_o03_dev.py and concise English compatibility documentation at library/docs/development-docutils-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/docutils/docutils/parsers/rst/directives/body.py
- library/tests/test_development_docutils_o03_dev.py
- library/docs/development-docutils-o03-dev.md
