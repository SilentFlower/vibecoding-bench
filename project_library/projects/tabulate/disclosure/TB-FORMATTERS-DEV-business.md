# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tabulate.formatters.tabulate_with_formatters(data,headers=(),*,formatters=(),**options). Reuse pinned normalization, then apply callable(value,data_row_index,column_index) or None per column before rendering through tabulate. Do not call formatters on separator rows or absent ragged cells; row indices count business rows only. Preserve original data, propagate callback errors, validate callbacks and excess columns, support keys/firstrow headers and original options including disable_numparse. Do not add a global formatter registry or alter tabulate signature.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_formatters_dev.py and concise English compatibility documentation at library/docs/development-tb-formatters-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tabulate/formatters.py
- library/development_tests/test_development_tb_formatters_dev.py
- library/docs/development-tb-formatters-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
