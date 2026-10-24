# Business scope

Fix enable_fts so a finite one-shot iterable of column names behaves like equivalent list/tuple throughout creation, initial population and optional triggers. Preserve the attached exact compatibility boundaries, tokenization, quoted identifiers and replace behavior. FTS4 existing update-trigger error is outside this change; retain FTS5 CRUD. Add focused public regressions within allowed paths.

# Investigation topics

- Explain the responsibilities of the content table, full-text index, and triggers.
- Choose between triggers and rebuilding to synchronize FTS5 search.
- Diagnose index creation failures caused by exhausting a one-shot column iterator.

# Supplied business material: materials/fts-context.md

# Search index context
Synthetic table notes has id INTEGER primary key, body TEXT and extra TEXT.
Rows: {"id":1,"body":"azure","extra":"keep"}, {"id":2,"body":"gold","extra":"azure hidden"}.
Call `table.enable_fts(["body"], fts_version="FTS5")`.
Explain content versus virtual table, initial population, optional triggers and Table.search. The nonindexed extra column is not searchable. Do not assume a universal number of FTS internal tables.


# Supplied business material: materials/fts-timeline.md

# FTS5 lifecycle timeline
Only FTS5 is covered by this operational recommendation.
`notes.enable_fts(["body"], fts_version="FTS5", create_triggers=False)` succeeds.
A later INSERT adds body='violet'; Table.search('violet') returns no result.
No index-build error occurred and columns is an ordinary list. Recommend an existing-API setup for a new continually written table and a separate rebuild operation for an existing index. Do not blindly call enable_fts twice on an existing table. Do not generalize FTS5 update/delete success to FTS4.


# Supplied business material: materials/fts-reproducer.py

from sqlite_utils import Database

db = Database(memory=True)
table = db["notes"].insert({"id": 1, "body": "azure"}, pk="id")
table.enable_fts(iter(["body"]), create_triggers=True)
print(list(table.search("azure")))


# Supplied business material: materials/fts-observed.txt

Equivalent list columns=['body'] succeeds. A finite iter(['body']) fails with sqlite3.OperationalError: near ")": syntax error while populating the virtual table. A notes_fts table remains after the failed call. Same pinned version and synthetic rows. Initial material is complete; no disclosure is required.


# Supplied business material: materials/fts-repair.md

# Authorized finite-iterable repair
Fix enable_fts for equivalent finite list, tuple, one-shot iterator and generator column names throughout SQL construction, initial population and optional triggers.
Preserve FTS4/FTS5, selected column order, quoted identifiers, empty tables, tokenize, return self and replace semantics. Replacing identical configuration must not issue DDL/writes; changed configuration must work. FTS4 initialization and subsequent INSERT remain compatible. Existing FTS4 UPDATE-trigger SQL logic error is an independent known limitation; this task does not repair it. Preserve actual FTS5 INSERT/UPDATE/DELETE search synchronization.
No infinite-stream support, transaction redesign or automatic cleanup of previously damaged user indices is requested. Do not swallow SQL errors or disable triggers. Add focused public regressions. Only library/sqlite_utils/db.py and library/tests/test_fts.py may change; private tests and environment are frozen. Start from the original scenario baseline, with no convert repair inherited.

