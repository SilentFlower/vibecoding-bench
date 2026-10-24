# Engineering contract: DATASET-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Table.insert_iter and update_iter for one-shot iterable mapping records, with positive non-bool chunk_size, ensure/types and explicit atomic:boolean. Buffer/copy at most one chunk and call real insert_many/update_many exactly once per chunk, allowing late new columns per original schema policy and preserving the accepted absent-field update behavior. Return consumed record count, not affected rows. Empty input creates no table, invalid options do not consume input, source/generator errors propagate. atomic=True wraps the entire DML in the existing Database transaction; default keeps committed chunks on later failure. Document backend DDL rollback limitations; original Sequence APIs stay unchanged.

Deliver meaningful original-failing public regression tests at library/test/test_development_dataset_o05_dev.py and concise English compatibility documentation at library/docs/development-dataset-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dataset/table.py
- library/test/test_development_dataset_o05_dev.py
- library/docs/development-dataset-o05-dev.md
