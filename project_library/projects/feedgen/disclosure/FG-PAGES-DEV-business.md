# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement feedgen.pagination.paginate(feed,page,page_size,base_url,*,order_by=None,reverse=True) returning frozen FeedPage(feed,number,total_pages,total_entries). Reuse completed deep copy and optional stable date ordering. Positive pages/sizes, one empty page for empty feed and explicit out-of-range errors. Preserve root feed ID/metadata/other link relations, replace only self/first/last/prev/next with correct HTTP(S) page URLs; replace duplicate page query parameters while preserving unrelated query pairs and fragments. Source entries/links stay unchanged and result must serialize through actual Atom.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_fg_pages_dev.py and concise English compatibility documentation at library/docs/development-fg-pages-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/feedgen/pagination.py
- library/development_tests/test_development_fg_pages_dev.py
- library/docs/development-fg-pages-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
