from tinydb import Query, TinyDB
from tinydb.storages import MemoryStorage


def load_rules():
    """Enumerate this finite set of configuration rules. @return Rule iterator."""
    yield ({'done': True}, Query().qty > 0)


for label in ('list', 'generator'):
    with TinyDB(storage=MemoryStorage) as db:
        db.insert_multiple([{'sku': 'A', 'qty': 1}, {'sku': 'B', 'qty': 2}])
        rules = list(load_rules()) if label == 'list' else load_rules()
        updated = db.update_multiple(rules)
        print(label, updated, [doc.get('done', False) for doc in db.all()])
