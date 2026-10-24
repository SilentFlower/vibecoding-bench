# Engineering contract: TB-DEDUP-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tablib.dedup.deduplicate(dataset,by,*,keep="first") using completed schema/key/copy semantics. by is an existing field or nonempty unique field list; keep first/last/False. Last retains last occurrence at its actual original position, False removes all members of duplicate groups. Composite keys are strict type/value (including None), reject mutable keys, preserve selected original row order and deep-copy title/cells/tags without source mutation. Empty headed datasets are valid, missing/duplicate key columns and invalid policies fail before producing output.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_dedup_dev.py and concise English compatibility documentation at library/docs/development-tb-dedup-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/tablib/dedup.py
- library/development_tests/test_development_tb_dedup_dev.py
- library/docs/development-tb-dedup-dev.md
