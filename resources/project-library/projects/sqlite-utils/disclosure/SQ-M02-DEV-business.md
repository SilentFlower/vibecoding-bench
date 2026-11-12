# Business scope

Fix Table.convert so each call uses the supplied callable, including consecutive dict.get, partial, callable-object and same-named function cases on the same Database. Preserve output, bound WHERE, falsey values, lambdas, multi, exceptions and the public register_function replace contract. Add focused public regressions within allowed paths.

# Investigation topics

- Plan a selective normalization pilot that preserves the original columns.
- Diagnose reuse of a stale callback with the same name across successive conversions.

# Supplied business material: materials/normalization-policy.md

# Conservative normalization pilot
Synthetic rows: {"id":1,"raw":"ca"}, {"id":2,"raw":"ny"}.
Pure conversion str.upper. Keep raw, write a separate normalized TEXT column, and pilot only id=1 using bound WHERE parameters. Untouched id=2 should have normalized NULL. Define backup, validation and expansion gates. Do not execute a migration or claim the added-column DDL and every future conversion necessarily share one rollback boundary.


# Supplied business material: materials/convert-reproducer.py

from sqlite_utils import Database

db = Database(memory=True)
table = db["places"].insert({"id": 1, "state": "CA", "country": "US"}, pk="id")
states = {"CA": "California"}
countries = {"US": "United States"}
table.convert("state", states.get)
table.convert("country", countries.get)
print(table.get(1))
# Compare a fresh database using two distinct lambdas, one per mapping.


# Supplied business material: materials/convert-observed.txt

Pinned original consecutive dict.get calls: {'id': 1, 'state': 'California', 'country': None}.
Fresh original with separate lambda wrappers: {'id': 1, 'state': 'California', 'country': 'United States'}.
The country mapping really contains US. Do not assume all conversion calls fail; compare registration names and current callback identity.


# Supplied business material: materials/convert-repair.md

# Authorized current-callback repair
Each Table.convert invocation must use its own supplied callable on the same Database, including consecutive bound dict.get, partial objects, callable instances and different same-named functions, both across columns and tables. Preserve distinct lambdas, repeated use of the same callback, multi, output, bound WHERE, falsey values and existing callback exception/transaction behavior. The supplied mappings are pure synchronous functions; arbitrary nested convert or concurrent cross-thread connection use is not a new guarantee.
Public Database.register_function has an established replace=False default: registering another same-name/same-arity function preserves the old SQL callback; only replace=True replaces it. Keep that public contract and its upstream test unchanged. Do not globally reset functions or special-case the supplied column names/data.
Only library/sqlite_utils/db.py, library/tests/test_convert.py and library/tests/test_register_function.py may change. Add focused public regressions. Frozen upstream tests are restored for independent regression. Start from the original scenario baseline, with no FTS iterable repair inherited.

