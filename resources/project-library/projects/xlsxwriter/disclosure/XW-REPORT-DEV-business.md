# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement xlsxwriter.report.export_report(destination,columns,records,*,sheet="Report",max_rows=1048576,workbook_options=None) and frozen ReportSummary(sheets,row_count). Reuse completed atomic_workbook, safe sheet naming and typed write_records. Stream records once, split at explicit per-sheet row budget including repeated headers, freeze first row, create one header-only sheet for empty input and return actual names/count only after successful replacement. Preserve UTC and literal-formula semantics in constant_memory mode. Any bad later record or source exception preserves the old target without partial report files. Validate budgets/schema before iterating.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xw_report_dev.py and concise English compatibility documentation at library/docs/development-xw-report-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xlsxwriter/report.py
- library/development_tests/test_development_xw_report_dev.py
- library/docs/development-xw-report-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
