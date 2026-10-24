# Engineering contract: XW-UTC-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement xlsxwriter.utc.as_utc(datetime,*,naive="raise") and write_utc(worksheet,row,col,value,cell_format=None,*,naive="raise"). Convert aware values by instant to naive UTC before actual write_datetime, preserving fractional seconds and input identity. Default rejects naive datetimes; explicit naive="utc" accepts them. Use utcoffset semantics and DST fold correctly, keep workbook 1900/1904 date modes and native return codes/formats, never globally enable remove_timezone or silently discard offsets. Existing write_datetime behavior stays compatible.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xw_utc_dev.py and concise English compatibility documentation at library/docs/development-xw-utc-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xlsxwriter/utc.py
- library/development_tests/test_development_xw_utc_dev.py
- library/docs/development-xw-utc-dev.md
