from tinydb import Query, TinyDB
from tinydb.storages import MemoryStorage

with TinyDB(storage=MemoryStorage) as db:
    db.insert_multiple([
        {'sku': 'A', 'billing': {'city': 'Oslo'}, 'shipping': {'city': 'Lima'}},
        {'sku': 'B', 'billing': {'city': 'Lima'}, 'shipping': {'city': 'Oslo'}},
    ])
    billing = Query().billing.fragment({'city': 'Oslo'})
    shipping = Query().shipping.fragment({'city': 'Oslo'})
    print('billing', [doc.doc_id for doc in db.search(billing)])
    print('shipping_after_billing', [doc.doc_id for doc in db.search(shipping)])
    print('shipping_direct', [doc.doc_id for doc in db.all() if shipping(doc)])
