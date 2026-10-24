# Engineering contract: CSVKIT-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add real csvkit.utilities.csvslice.CSVSlice and python -m entry using CSVKitUtility reader/writer conventions. Support zero-based nonnegative --start/--stop and positive --step (exclusive stop) through lazy islice, or mutually compatible --tail N through bounded deque, with tail=0 emitting only header. Preserve complete quoted/multiline records, dialect/encoding/skip/headerless options and exactly one header. Reject negative ranges, zero step and combined tail/range modes before output, support empty/header-only inputs and never preload ordinary forward slices.

Deliver meaningful original-failing public regression tests at library/tests/test_development_csvkit_o04_dev.py and concise English compatibility documentation at library/docs/development-csvkit-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/csvkit/utilities/csvslice.py
- library/tests/test_development_csvkit_o04_dev.py
- library/docs/development-csvkit-o04-dev.md
