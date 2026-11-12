# Engineering contract: MARKDOWNIFY-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Integrate include_selectors/exclude_selectors into actual convert_soup. None include means the whole remaining tree, an empty include sequence means no content; accept a selector string or sequence. Work on a detached copy whenever selection is requested, apply exclusions before inclusions and truly remove excluded descendants. Emit selected roots in original document order, deduplicate overlapping selectors and ancestor/descendant selections by node identity, and preserve caller-supplied BeautifulSoup unmodified. Invalid selectors must propagate rather than silently selecting all. Keep default conversion and existing strip/convert tag-format semantics intact.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdownify_o04_dev.py and concise English compatibility documentation at library/docs/development-markdownify-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdownify/__init__.py
- library/tests/test_development_markdownify_o04_dev.py
- library/docs/development-markdownify-o04-dev.md
