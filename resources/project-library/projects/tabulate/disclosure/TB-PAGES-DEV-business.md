# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tabulate.pages.iter_pages(rows,page_size,headers=(),*,showindex=False,**options). Lazily read one-shot rows, count data rows excluding separators, render each page with the pinned tabulate and repeat explicit headers or consume firstrow headers once. Automatic indices are global zero-based business indices across pages; separators retain order and boundary separators belong to the next page. Never prefetch the next data row before yielding a full page; emit no empty final page. Validate positive integer size and supported automatic-index/header options; leave arbitrary custom index streams out of this API.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_pages_dev.py and concise English compatibility documentation at library/docs/development-tb-pages-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tabulate/pages.py
- library/development_tests/test_development_tb_pages_dev.py
- library/docs/development-tb-pages-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
