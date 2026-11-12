# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add csvkit.utilities.csvfind.find_columns and actual CSVFind utility/module entry using CSVKitUtility and native FilteringCSVReader predicates. Accept exact --value (including empty) or explicit --regex, selected columns and nonnegative bounded --sample-size; scan logical records once and report every selected column by zero-based index/name/count plus bounded 1-based logical data-row samples. Duplicate column names remain distinct. JSON schema=1 reports rows and columns; CSV output respects --zero only for displayed column indexes. Preserve cells, handle short rows as native empty missing fields, empty inputs, no matches and generator errors; never rescan per column or silently drop matches beyond sample budget.

Deliver meaningful original-failing public regression tests at library/tests/test_development_csvkit_o06_dev.py and concise English compatibility documentation at library/docs/development-csvkit-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/csvkit/utilities/csvfind.py
- library/tests/test_development_csvkit_o06_dev.py
- library/docs/development-csvkit-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
