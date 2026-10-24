# Engineering contract: MARKDOWNIFY-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add base_url and url_transform options integrated into real a/img/video/source-fallback/poster conversion. Use urllib.parse.urljoin for nonempty relative destinations with a string base while preserving fragment-only references, empty destinations and absolute URI semantics. Call optional transform(resolved_url, kind) exactly once per actual nonempty destination, with kind link/image/video/poster, after resolution; a None result suppresses that destination and invalid return types raise TypeError. Preserve titles, inline-image rules, autolinks, source ordering and default output. Perform no network requests.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdownify_o03_dev.py and concise English compatibility documentation at library/docs/development-markdownify-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdownify/__init__.py
- library/tests/test_development_markdownify_o03_dev.py
- library/docs/development-markdownify-o03-dev.md
