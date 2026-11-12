# Engineering contract: CSVKIT-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement csvkit.headers.rename_columns(names,mapping,*,collision="error") and actual CSVCut --rename-columns-json / --rename-collision=error|suffix. Validate exact unique original source names, nonempty string targets and unknown mappings, apply against the full original header before projecting originally selected columns and change no cell values. Reject collisions by default; suffix mode preserves first occurrence and avoids all reserved eventual target names. Reject headerless rename before output, invalid JSON/shapes and ambiguous duplicate source names. Keep old cut/default headers, order and mapping inputs unchanged.

Deliver meaningful original-failing public regression tests at library/tests/test_development_csvkit_o05_dev.py and concise English compatibility documentation at library/docs/development-csvkit-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/csvkit/headers.py
- library/csvkit/utilities/csvcut.py
- library/tests/test_development_csvkit_o05_dev.py
- library/docs/development-csvkit-o05-dev.md
