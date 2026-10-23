# Business scope

Repair the supplied cachedmethod class-access inconsistency under the complete public receiver contract. Support the original receiver parameter name without hardcoding self. Preserve valid bound/positional calls, info and independent instances; keep positional-only, missing and duplicate receiver rejection. Modify only the authorized implementation and public test file, and deliver meaningful original-failing public regression tests.

# Investigation topics

- 定位类访问的关键字receiver绑定差异

# Supplied business material: materials/receiver-reproducer.py

from cachetools import cachedmethod

class Catalog:
    """复现类入口与实例入口的调用差异。"""
    def __init__(self):
        """创建独立缓存。@return None。"""
        self.cache = {}

    @cachedmethod(lambda obj: obj.cache)
    def quote(self, sku):
        """返回业务参数。@param sku 商品。@return 商品。"""
        return sku

catalog = Catalog()
print(catalog.quote(sku="coffee"))
print(Catalog.quote(catalog, sku="coffee"))
print(Catalog.quote(self=catalog, sku="coffee"))


# Supplied business material: materials/receiver-contract.md

Repair class access to cachedmethod when the original receiver parameter can be supplied by keyword.
Use the receiver's actual parameter name, which need not be self. Preserve positional and bound calls,
business arguments, instance isolation and info counters. A positional-only receiver must still reject
keyword binding. Missing and duplicate receivers must still raise TypeError. Do not change signatures,
dependencies, unrelated descriptors, pytest controls or global settings. Deliver meaningful public
regression tests in library/tests/test_cachedmethod.py that fail on the pinned original and pass after
the repair. Only library/src/cachetools/_descriptor.py and that public test file are authorized.

