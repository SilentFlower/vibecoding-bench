# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tabulate.accessibility.accessible_html(data,headers=(),*,caption=None,table_id=None,row_headers=False,**options). Render via safe html format, add escaped caption/optional quoted id, scope=col to real column header th elements and optional scope=row to the first cell of each body row. Preserve other cells, alignment and data escaping; never convert escaped user markup into actual tags. Reject overriding tablefmt, nonboolean row_headers and invalid caption/id values before rendering. Keep old html/unsafehtml output unchanged and do not alter tabulate public signature.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_accessible_html_dev.py and concise English compatibility documentation at library/docs/development-tb-accessible-html-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tabulate/accessibility.py
- library/development_tests/test_development_tb_accessible_html_dev.py
- library/docs/development-tb-accessible-html-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
