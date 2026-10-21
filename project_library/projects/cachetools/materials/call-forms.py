from cachetools import cached

calls = []

@cached(cache={}, info=True)
def quote(quantity=1):
    """记录实际求值。@param quantity 数量。@return 数量。"""
    calls.append(quantity)
    return quantity

quote()
quote(1)
quote(quantity=1)
print(calls)
print(quote.cache_info())
