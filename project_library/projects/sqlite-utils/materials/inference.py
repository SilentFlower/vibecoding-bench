from sqlite_utils import Database

db = Database(memory=True)
rows = ({"id": i, "code": i} if i < 200 else {"id": 200, "code": "007"} for i in range(201))
table = db["orders"].insert_all(rows, pk="id")
print(table.schema)
print(table.get(200))
db.close()
