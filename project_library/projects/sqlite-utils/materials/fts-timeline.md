# FTS5 lifecycle timeline
Only FTS5 is covered by this operational recommendation.
`notes.enable_fts(["body"], fts_version="FTS5", create_triggers=False)` succeeds.
A later INSERT adds body='violet'; Table.search('violet') returns no result.
No index-build error occurred and columns is an ordinary list. Recommend an existing-API setup for a new continually written table and a separate rebuild operation for an existing index. Do not blindly call enable_fts twice on an existing table. Do not generalize FTS5 update/delete success to FTS4.
