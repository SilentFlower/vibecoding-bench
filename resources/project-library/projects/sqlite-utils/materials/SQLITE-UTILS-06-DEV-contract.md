# Engineering contract: SQLITE-UTILS-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add Queryable.export_csv(stream,columns=None,where=None,where_args=None,order_by=None,limit=None,offset=None,dialect="excel"), available on real Table/View. Validate requested column order/no duplicates against actual schema before writing, then csv.writer header and iterate rows_where lazily with quoted selected identifiers and bound where_args. Return actual data row count; empty table still header, Unicode/commas/quotes/multiline fields roundtrip through csv.reader, NULL follows CSV empty-field convention. Never close caller stream, materialize all rows, mutate DB or claim lossless SQLite type encoding. Existing CLI export remains.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlite_utils_06_dev.py, and English compatibility documentation at library/docs/development-sqlite-utils-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlite_utils/db.py
- library/tests/test_development_sqlite_utils_06_dev.py
- library/docs/development-sqlite-utils-06-dev.md
