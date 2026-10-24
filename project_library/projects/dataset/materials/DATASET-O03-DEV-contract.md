# Engineering contract: DATASET-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement Table.increment(column,amount,filters,*,nulls="preserve") with one SQLAlchemy UPDATE expression, never read-modify-write. Require existing numeric SQLAlchemy column, finite int/float/Decimal excluding bool, explicit filters mapping, and nulls=preserve|zero. Zero/negative increments work; unmatched/nonexistent table returns zero, no schema creation. Return reliable database rowcount, preserve existing update/transaction behavior and reject unknown/non-numeric columns or invalid policies before DML. Prove two file-backed SQLite connections accumulate changes and an explicit database transaction rolls back failed work; document backend numeric range/precision limits.

Deliver meaningful original-failing public regression tests at library/test/test_development_dataset_o03_dev.py and concise English compatibility documentation at library/docs/development-dataset-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dataset/table.py
- library/test/test_development_dataset_o03_dev.py
- library/docs/development-dataset-o03-dev.md
