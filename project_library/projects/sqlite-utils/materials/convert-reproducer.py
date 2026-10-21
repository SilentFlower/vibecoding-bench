from sqlite_utils import Database

db = Database(memory=True)
table = db["places"].insert({"id": 1, "state": "CA", "country": "US"}, pk="id")
states = {"CA": "California"}
countries = {"US": "United States"}
table.convert("state", states.get)
table.convert("country", countries.get)
print(table.get(1))
# Compare a fresh database using two distinct lambdas, one per mapping.
