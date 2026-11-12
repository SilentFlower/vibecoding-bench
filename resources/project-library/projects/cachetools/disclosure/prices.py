from cachetools import cachedmethod

class Prices:
    """模拟一个对象中的两种业务报价。"""
    def __init__(self):
        """创建共享缓存。@return None。"""
        self.cache = {}

    @cachedmethod(lambda obj: obj.cache)
    def retail(self, sku):
        """返回零售价。@param sku 商品。@return 金额。"""
        return 100

    @cachedmethod(lambda obj: obj.cache)
    def wholesale(self, sku):
        """返回批发价。@param sku 商品。@return 金额。"""
        return 90

prices = Prices()
print(prices.retail("coffee"))
print(prices.wholesale("coffee"))
