# Engineering contract: CH-FORMULA-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add spreadsheet_formula_policy(data,headers,formula_policy="preserve",**kwargs) preprocessor. Treat string cells/headers whose leading-whitespace-trimmed text begins =,+,-,@ as formula-like. Preserve default; escape prefixes one apostrophe to the exact original string; error raises with only one-based data row/column (header row zero), without exposing contents. Keep numeric negatives/nonstrings unchanged, operate lazily without mutating inputs and integrate through real CSV formatter preprocessors. Per-call policy must not leak to subsequent exports. Do not claim sanitization for every spreadsheet engine or rollback lines already consumed before a later error.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ch_formula_dev.py and concise English compatibility documentation at library/docs/development-ch-formula-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cli_helpers/tabular_output/preprocessors.py
- library/development_tests/test_development_ch_formula_dev.py
- library/docs/development-ch-formula-dev.md
