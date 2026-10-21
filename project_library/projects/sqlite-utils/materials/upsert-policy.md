# Repeatable import policy
Stable order IDs are TEXT keys, for example 001 and 002. Each finite input file has unique IDs.
Existing row: {"id":"001","qty":1,"memo":"keep"}.
Incoming rows: [{"id":"001","qty":5},{"id":"002","qty":2}].
Each rerun replaces supplied quantity; omitted memo must remain for existing records and is NULL for new rows.
Plan with existing APIs, validation, explicit prospective schema, backups and checks. Do not execute a migration. No promise of whole-stream atomicity or reconstructing previously lost data is requested.
