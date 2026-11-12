# Engineering contract: TB-JOIN-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tablib.joining.join(left,right,on,*,how="left",suffixes=("_left","_right"),nulls="never",max_rows=100000) using completed static schema/key/copy semantics. Support inner/left/full outer, composite same-name keys, strict typed keys, many-to-many in stable left then right order and unmatched right rows last. Default None keys never match; equal is explicit. Omit repeated right join keys, populate left key columns on unmatched right rows, suffix colliding nonkeys and reject resulting name collisions. Preserve copied cells/title and combined row tags; fail before return on output budget overflow or mutable key, leaving both inputs unchanged.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_join_dev.py and concise English compatibility documentation at library/docs/development-tb-join-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/tablib/joining.py
- library/development_tests/test_development_tb_join_dev.py
- library/docs/development-tb-join-dev.md
