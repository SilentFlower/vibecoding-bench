from cachetools import cachedmethod

class Catalog:
    """Reproduce the difference between class access and instance access."""
    def __init__(self):
        """Create an independent cache. @return None."""
        self.cache = {}

    @cachedmethod(lambda obj: obj.cache)
    def quote(self, sku):
        """Return the business argument. @param sku Product identifier. @return Product identifier."""
        return sku

catalog = Catalog()
print(catalog.quote(sku="coffee"))
print(Catalog.quote(catalog, sku="coffee"))
print(Catalog.quote(self=catalog, sku="coffee"))
