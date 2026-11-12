from boltons.iterutils import unique, redundant

values = ["A", "a", "a", "B", "b"]
print(unique(values, key=str.lower))
print(redundant(values, key=str.lower))
print(redundant(values, key=str.lower, groups=True))

class CaseKey:
    """A valid business normalizer whose own truth value is False."""
    def __call__(self, value):
        """Return the business key. @param value Original value. @return Lowercase value."""
        return value.lower()

    def __bool__(self):
        """Represent a falsey object. @return False."""
        return False

print(redundant(values, key=CaseKey()))
