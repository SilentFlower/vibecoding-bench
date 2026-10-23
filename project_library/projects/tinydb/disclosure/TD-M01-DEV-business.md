# Business scope

Fix the nested fragment query-cache collision demonstrated here. Queries with the same fragment on different complete field paths must return their own matching documents regardless of evaluation order. Preserve root-level fragments, missing-field behavior, normal query caching, and the uncacheable map-path contract. Add focused public regression coverage without changing storage APIs or private verification files. The attached reproduction is sufficient; no earlier answer is required.

# Investigation topics

- 先补材料，再辨别共享缓存文档的正常约定
- 定位不同嵌套字段 fragment 查询的缓存串用

# Supplied business material: materials/tags-report.md

# Initial incident report
An order's tags seem to change after a search. The reporter has not provided the caller, the storage configuration, the before/after values, or whether anything was written to storage. Please request the evidence needed to distinguish possible causes. Do not presume a library defect from this symptom alone.


# Supplied business material: materials/fragment-reproducer.py

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


# Supplied business material: materials/fragment-observed.txt

Frozen upstream observation with the attached two orders:
billing [1]
shipping_after_billing [1]
shipping_direct [2]
The same discrepancy is reproduced with JSONStorage. Clearing the query cache before the shipping search gives [2]. Reversing the query order lets the first shipping result contaminate billing instead. Diagnose this frozen original-version observation before any repair.


# Supplied business material: materials/fragment-repair.md

# Authorized repair
The supplied fragment reproducer is self-contained; completing another task is not a prerequisite. Queries with identical fragments on different complete paths must keep separate cache identities and results in either order. Preserve ordinary query cache use, root/empty fragments, missing-field behavior, Boolean composition, and the uncacheable map-path contract. Add meaningful public regression tests. Only library/tinydb/queries.py, library/tests/test_queries.py and library/tests/test_tables.py are authorized. Do not change storage, private verification, configuration, or dependencies.


# Supplied business material: disclosure/tags-unavailable.md

# Reporter follow-up: requested evidence is unavailable
The caller script, storage configuration, original database file, and complete before/after record were lost. The reporter cannot provide a reproducer or any further incident materials. The only surviving information is the initial symptom. Conclude within that limitation: explain what cannot be established, name the missing evidence and a safe verification plan, and do not claim to have identified or reproduced the cause. No reproduction material is available for this entry.

