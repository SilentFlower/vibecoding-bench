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
