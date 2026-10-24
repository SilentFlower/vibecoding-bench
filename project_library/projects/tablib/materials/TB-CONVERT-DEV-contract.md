# Engineering contract: TB-CONVERT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tablib.conversion.convert_columns(dataset,converters,*,errors="raise") returning frozen ConversionResult(dataset,errors) and CellError(row,column,error_type,message). Use completed schema/copy semantics and actual raw cells in deterministic row then header order. Converters receive independent cell copies so mutation or late failures cannot affect source. Raise mode wraps ValueError/TypeError/OverflowError with row/name context; collect keeps original failed cell copy and continues while successful conversions survive. Preserve title/tags, reject unknown/noncallable columns and invalid strategies, propagate unrelated programming exceptions and store no traceback.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_convert_dev.py and concise English compatibility documentation at library/docs/development-tb-convert-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/tablib/conversion.py
- library/development_tests/test_development_tb_convert_dev.py
- library/docs/development-tb-convert-dev.md
