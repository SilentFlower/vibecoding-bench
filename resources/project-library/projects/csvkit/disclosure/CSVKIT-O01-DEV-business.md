# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement csvkit.cleaning.clean_rows(reader, *,max_rows=10000,max_errors=1000,**RowChecker_options), clean_file(stream,reader_options=None,**options), immutable CleanResult(schema,header,rows,errors) and CleanIssue(line_number,code,message). Reuse the actual RowChecker and agate reader, including physical multiline line numbers and late empty-column removal, without returning before file-level checks. Do not retain raw error rows, close caller streams, write stdout/stderr or call sys.exit. Enforce nonnegative non-bool budgets, conflicting fixes, full completion and explicit CleanLimitError instead of partial success; propagate IO/errors. Preserve RowChecker/CLI APIs.

Deliver meaningful original-failing public regression tests at library/tests/test_development_csvkit_o01_dev.py and concise English compatibility documentation at library/docs/development-csvkit-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/csvkit/cleaning.py
- library/tests/test_development_csvkit_o01_dev.py
- library/docs/development-csvkit-o01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
