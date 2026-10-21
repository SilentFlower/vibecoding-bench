from cachetools import Cache

cache = Cache(maxsize=5, getsizeof=len)
rows = ["coffee"]
cache["rows"] = rows
rows.append("tea")
print(cache.currsize, len(cache["rows"]))
cache["rows"] = rows
print(cache.currsize)
