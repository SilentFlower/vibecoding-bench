# Engineering contract: AG-SHIFT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add exported Lag and Lead Computation classes with (column_name, offset=1, default=None, partition_by=None). Use existing row order, including interleaved partitions, without sorting or mutating the table. Offset must be a nonnegative non-bool integer; zero copies the original column. partition_by accepts a column name or finite unique list/tuple of column names. Validate names and cast the boundary default with the original DataType; return a column of that same type and original length. Nulls remain positional values and oversized offsets fill the default. Preserve existing Change and other computations.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ag_shift_dev.py and concise English compatibility documentation at library/docs/development-ag-shift-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/agate/computations/shift.py
- library/agate/computations/__init__.py
- library/development_tests/test_development_ag_shift_dev.py
- library/docs/development-ag-shift-dev.md
