# Conservative normalization pilot
Synthetic rows: {"id":1,"raw":"ca"}, {"id":2,"raw":"ny"}.
Pure conversion str.upper. Keep raw, write a separate normalized TEXT column, and pilot only id=1 using bound WHERE parameters. Untouched id=2 should have normalized NULL. Define backup, validation and expansion gates. Do not execute a migration or claim the added-column DDL and every future conversion necessarily share one rollback boundary.
