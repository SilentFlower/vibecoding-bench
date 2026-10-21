from sqlite_utils import Database

db = Database(memory=True)
table = db["notes"].insert({"id": 1, "body": "azure"}, pk="id")
table.enable_fts(iter(["body"]), create_triggers=True)
print(list(table.search("azure")))
