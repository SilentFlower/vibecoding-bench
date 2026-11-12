from tinydb import Query, TinyDB
from tinydb.operations import increment
from tinydb.storages import MemoryStorage

with TinyDB(storage=MemoryStorage) as db:
    db.insert_multiple([{'sku': 'A', 'qty': 0}, {'sku': 'B', 'qty': 0}])
    rules = [(increment('qty'), Query().qty == 0), ({'stage': 'ready'}, Query().qty == 1)]
    print('updated_ids', db.update_multiple(rules))
    print('orders', db.all())
