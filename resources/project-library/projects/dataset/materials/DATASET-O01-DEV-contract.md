# Engineering contract: DATASET-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix actual Table.update_many ensure/types handling before compiling SQL. Validate every input match key and positive non-bool chunk_size before any schema/DML change, synchronize the union with explicit type overrides, retain ensure=False column-dropping semantics and make empty input a no-op. Group rows by present update fields rather than padding absent fields to NULL; safe generated key binds cannot collide with real column names. Preserve existing literals, chunk commits and row inputs; empty/duplicate matching keys fail. Demonstrate real SQLite schema/type and row state, including a late missing key causing no earlier DML/DDL.

Deliver meaningful original-failing public regression tests at library/test/test_development_dataset_o01_dev.py and concise English compatibility documentation at library/docs/development-dataset-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dataset/table.py
- library/test/test_development_dataset_o01_dev.py
- library/docs/development-dataset-o01-dev.md
