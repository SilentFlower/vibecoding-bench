# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement xlsxwriter.sheet_names.add_named_worksheet(workbook,desired). Sanitize Excel forbidden characters/control chars, trim whitespace and leading/trailing apostrophes, provide fallback Sheet, avoid reserved History and limit to 31 Unicode codepoints. Compare against actual workbook.worksheets names case-insensitively with casefold, allocate stable " (2)" suffixes while re-truncating base. Return the actual new worksheet and never rename/overwrite existing sheets. Handle long names, all-invalid names, repeated collisions and inputs differing only by case.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xw_sheet_names_dev.py and concise English compatibility documentation at library/docs/development-xw-sheet-names-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xlsxwriter/sheet_names.py
- library/development_tests/test_development_xw_sheet_names_dev.py
- library/docs/development-xw-sheet-names-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
