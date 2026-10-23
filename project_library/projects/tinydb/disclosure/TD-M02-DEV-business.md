# Business scope

Make update_multiple apply a finite one-shot iterable of update rules to all matching documents just as it applies an equivalent list or tuple. Preserve rule order, in-place callback behavior, repeated returned IDs, and existing storage interfaces. If enumerating the rules fails, no part of those rules should have been applied. Add focused public regressions; do not introduce general transaction semantics or modify private verification files. The attached reproduction is self-contained; this scene starts from the original baseline.

# Investigation topics

- 解释多规则顺序和重复返回文档 ID
- 定位一次性规则流只更新第一单的原因

# Supplied business material: materials/rule-order.py

from tinydb import Query, TinyDB
from tinydb.operations import increment
from tinydb.storages import MemoryStorage

with TinyDB(storage=MemoryStorage) as db:
    db.insert_multiple([{'sku': 'A', 'qty': 0}, {'sku': 'B', 'qty': 0}])
    rules = [(increment('qty'), Query().qty == 0), ({'stage': 'ready'}, Query().qty == 1)]
    print('updated_ids', db.update_multiple(rules))
    print('orders', db.all())


# Supplied business material: materials/rule-order-observed.txt

updated_ids [1, 1, 2, 2]
orders [{'sku': 'A', 'qty': 1, 'stage': 'ready'}, {'sku': 'B', 'qty': 1, 'stage': 'ready'}]
There are still exactly two orders. This report uses a reusable list of rules.


# Supplied business material: materials/generator-reproducer.py

from tinydb import Query, TinyDB
from tinydb.storages import MemoryStorage


def load_rules():
    """枚举本次有限配置规则。@return 规则迭代器。"""
    yield ({'done': True}, Query().qty > 0)


for label in ('list', 'generator'):
    with TinyDB(storage=MemoryStorage) as db:
        db.insert_multiple([{'sku': 'A', 'qty': 1}, {'sku': 'B', 'qty': 2}])
        rules = list(load_rules()) if label == 'list' else load_rules()
        updated = db.update_multiple(rules)
        print(label, updated, [doc.get('done', False) for doc in db.all()])


# Supplied business material: materials/generator-observed.txt

list [1, 2] [True, True]
generator [1] [True, False]
Both input documents satisfy qty > 0 when the predicate is applied directly. The JSONStorage control produces the same discrepancy. Diagnose this frozen original-version behavior before any repair.


# Supplied business material: materials/generator-repair.md

# Authorized repair
The rule loader supplies a finite, small rule sequence. Make list, tuple, iterator and generator inputs equivalent for every document. Preserve rule order, callbacks that mutate their document, and repeated returned IDs (one entry per matching rule). Fully enumerate this call's rules before applying any of them: if enumeration raises, no rule may have changed documents or the persisted file. This does not request a transaction guarantee for arbitrary callback failures. Add meaningful public regression tests. Only library/tinydb/table.py and library/tests/test_tinydb.py are authorized; do not change storage, private verification, configuration, or dependencies. This reproduction is self-contained and does not require another task's answer or code.

