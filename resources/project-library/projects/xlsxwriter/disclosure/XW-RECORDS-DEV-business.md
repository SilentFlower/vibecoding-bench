# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement xlsxwriter.records.Column(key,header,kind="auto",cell_format=None) and write_records(worksheet,start_row,columns,records,*,start_col=0,headers=True,missing="blank"). Use actual typed worksheet methods, never generic write for strings, so formula-looking and URL-looking text remain literal; only kind="formula" executes explicit formulas. Support strict number/boolean/text/datetime_utc/auto, None blanks, UTC feature, header aliases/formats and missing blank/raise. Prevalidate each complete row before its first cell, reject duplicate columns/oversize text/nonfinite values and bounds, detect write return failures, consume records once without whole-input buffering. Return count.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xw_records_dev.py and concise English compatibility documentation at library/docs/development-xw-records-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xlsxwriter/records.py
- library/development_tests/test_development_xw_records_dev.py
- library/docs/development-xw-records-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
