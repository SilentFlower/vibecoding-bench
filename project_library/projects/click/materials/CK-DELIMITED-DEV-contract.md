# Engineering contract: CK-DELIMITED-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement click.delimited.DelimitedList(item_type=str,*,separator=",",min_items=0,max_items=None) as ParamType, converting one CSV-style record or preexisting list/tuple to a tuple through the pinned item ParamType. Support quoted separators, escaped double quotes and explicit empty fields; empty text is an empty list. Reject malformed quotes, multiple records, invalid separators and invalid length bounds before invoking target commands. Preserve item BadParameter context and report one-based failing item position. Verify real option parsing and multiple=True without changing existing Tuple/Choice behavior.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ck_delimited_dev.py and concise English compatibility documentation at library/docs/development-ck-delimited-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/click/delimited.py
- library/development_tests/test_development_ck_delimited_dev.py
- library/docs/development-ck-delimited-dev.md
