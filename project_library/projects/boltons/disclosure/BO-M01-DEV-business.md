# Business scope

Implement the complete public falsey-key contract for redundant, including grouped output and zero-length callables over unhashable records. Preserve original values/order, None/default and errors. Modify only the authorized implementation/test files with meaningful original-failing public tests.

# Investigation topics

- Explain reporting of unique items and the first duplicate.
- Select business duplicate rules using the existing key parameter.
- Diagnose why a falsey normalizer is ignored.

# Supplied business material: materials/redundancy.py

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


# Supplied business material: materials/key-contract.md

Repair redundant so every supported non-None key is used even when a callable has false __bool__ or zero __len__. Preserve the public signature, None identity default, normal callables and attribute-name shorthand, original duplicate values, first-redundancy group order and exception propagation. Support falsey callables that map unhashable business records to hashable keys. Keep both groups=False and groups=True. Do not sort or replace the source values with normalized keys, change other iterator utilities, or alter dependencies/test controls. Only library/boltons/iterutils.py and library/tests/test_iterutils.py may change. Add meaningful original-failing public regressions and preserve all frozen original doctests/main/subtests.

