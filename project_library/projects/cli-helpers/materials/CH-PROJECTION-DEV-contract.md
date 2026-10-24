# Engineering contract: CH-PROJECTION-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement cli_helpers.tabular_output.projection.select_columns(data,headers,selection) returning (lazy_rows,projected_headers). Materialize finite headers once and validate ordered integer indices or unique string column names before row consumption. Preserve duplicate selected positions and exact raw values; reject ambiguous/missing names, bool/negative/out-of-range indices and malformed row widths with one-based row number. Do not mutate or stringify inputs. Project before the existing formatter so its type inference applies to the selected/reordered columns; verify JSON and delimited pipeline integration.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ch_projection_dev.py and concise English compatibility documentation at library/docs/development-ch-projection-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cli_helpers/tabular_output/projection.py
- library/development_tests/test_development_ch_projection_dev.py
- library/docs/development-ch-projection-dev.md
