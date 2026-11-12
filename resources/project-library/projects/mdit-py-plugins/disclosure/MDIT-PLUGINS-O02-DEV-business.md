# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix _attr_inline_rule class accumulation after link_close/span_close by resolving the matching opening Token before reading existing class. Link/image/code class blocks concatenate in declaration order without deduplication; spans preserve existing canonical repeated-attribute behavior by retaining each class word at its first position. Later id and other keys override normally. Keep single-token handling, nested inline content, neighbor isolation and allowed filtering. Do not globally concatenate nonclass attributes or mutate the closing Token instead of the rendered target.

Deliver meaningful original-failing public regression tests at library/tests/test_development_mdit_plugins_o02_dev.py and concise English compatibility documentation at library/docs/development-mdit-plugins-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/mdit_py_plugins/attrs/index.py
- library/tests/test_development_mdit_plugins_o02_dev.py
- library/docs/development-mdit-plugins-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
