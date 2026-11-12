import json
import sys
from tinydb import Query, TinyDB

path = sys.argv[1]
with TinyDB(path) as db:
    orders = db.table('orders')
    orders.insert({'sku': 'A', 'tags': ['new']})
    condition = Query().sku == 'A'
    first = orders.search(condition)
    first[0]['tags'].append('review')
    print('second_search', json.dumps(orders.search(condition), sort_keys=True))
    orders.clear_cache()
    print('after_clear_cache', json.dumps(orders.search(condition), sort_keys=True))
with TinyDB(path) as db:
    print('after_reopen', json.dumps(db.table('orders').all(), sort_keys=True))
