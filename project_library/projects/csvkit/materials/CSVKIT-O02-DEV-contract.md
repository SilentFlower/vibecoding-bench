# Engineering contract: CSVKIT-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add --ignore-case to actual CSVGrep without stealing -i/invert-match. Preserve existing -m substring semantics using Unicode casefold on pattern/cell, -f whole-cell exact membership using casefold and regex mode using re.IGNORECASE (not regex casefold rewriting). Preserve default case sensitivity, any/all, inverse, header and short-row behavior; support empty regex and empty substring coherently. Keep output cell bytes/text unchanged and close match files. Demonstrate real utility output including Unicode casefold and regex-specific differences.

Deliver meaningful original-failing public regression tests at library/tests/test_development_csvkit_o02_dev.py and concise English compatibility documentation at library/docs/development-csvkit-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/csvkit/utilities/csvgrep.py
- library/tests/test_development_csvkit_o02_dev.py
- library/docs/development-csvkit-o02-dev.md
