import sys
from pathlib import Path
from tinydb import TinyDB
from tinydb.middlewares import CachingMiddleware
from tinydb.storages import JSONStorage

path = Path(sys.argv[1])
db = TinyDB(path, storage=CachingMiddleware(JSONStorage))
db.table('orders').insert({'sku': 'A', 'qty': 1})
print('before_flush_or_close_bytes', path.stat().st_size)
db.storage.flush()
print('after_flush_bytes', path.stat().st_size)
db.close()
