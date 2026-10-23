# Business scope

Implement only the explicit generic-conversion opt-out contract and saved-package public regressions. Preserve defaults,explicit APIs and original tests.

# Investigation topics



# Supplied business material: materials/optout-repair.md

Explicit repair authorization: change only library/xlsxwriter/worksheet.py and add app/test_formula_optout.py. With strings_to_formulas=False,generic write must keep both ordinary =1+2 and braced {=SUM(1,2)} strings literal. Pinned original ignores the flag for braced array strings. Preserve default-enabled generic detection for both forms,explicit write_formula/write_array_formula behavior regardless of generic conversion flag,write_string literal behavior,number/string/URL dispatch and all original tests. Do not disable all formulas or alter literal text. Add meaningful public unittest regressions that inspect the saved XLSX XML/shared strings; no spreadsheet engine or external links.

