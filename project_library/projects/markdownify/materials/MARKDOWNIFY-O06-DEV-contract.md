# Engineering contract: MARKDOWNIFY-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add actual MarkdownConverter.convert_with_options(html, **overrides), leaving convert(html) and subclass convert_* signatures intact. Reuse subclass behavior without rerunning a potentially required-argument constructor; isolate nested dict/list/tuple/set configuration containers from both base and caller overrides while preserving opaque callbacks by identity. Normalize bs4_options as the constructor does, enforce strip/convert exclusion, and build fresh conversion-function cache bound to this isolated converter. Previously cached base methods, sequential calls, simultaneous calls and callback/errors must not mutate base options/cache or caller option containers. Demonstrate actual differing converted documents, not just returned option dictionaries.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdownify_o06_dev.py and concise English compatibility documentation at library/docs/development-markdownify-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdownify/__init__.py
- library/tests/test_development_markdownify_o06_dev.py
- library/docs/development-markdownify-o06-dev.md
