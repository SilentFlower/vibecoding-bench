# Search index context
Synthetic table notes has id INTEGER primary key, body TEXT and extra TEXT.
Rows: {"id":1,"body":"azure","extra":"keep"}, {"id":2,"body":"gold","extra":"azure hidden"}.
Call `table.enable_fts(["body"], fts_version="FTS5")`.
Explain content versus virtual table, initial population, optional triggers and Table.search. The nonindexed extra column is not searchable. Do not assume a universal number of FTS internal tables.
