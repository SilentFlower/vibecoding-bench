# Right join-key identity contract

The pinned implementation accepts right-key names and integer indices, including a sequence of them. Two distinct right columns may contain exactly the same values. The selected key must be the actual resolved column, never the first equal-valued column.

* Composite integer or mixed name/index keys must match the same rows as their equivalent name-only keys, retaining left row order and duplicate matches.
* With implicit right projection, omit only the resolved right key columns. A non-key copy column with equal values must remain. Negative indices resolve using existing column indexing.
* Explicit `columns` retains its existing projection semantics, including explicitly requested keys. `full_outer=True` keeps all right columns, including keys, and includes unmatched rows.
* Name-only, callable and sequential keys, left/inner joins, and `require_match` keep their existing semantics. Do not change table or Column equality or mutate the inputs.

Implement in `library/agate/table/join.py`; deliver original-failing public regression tests in `library/tests/test_development_join_keys.py`. Existing tests and test controls are frozen. No dependency changes.

Run the supplied reproduction with `PYTHONPATH=library python materials/development-reproducer.py` from a workspace with the materials available; its positional composite join currently raises ValueError, and its duplicate-valued-column case currently drops `copy` instead of `key`.
