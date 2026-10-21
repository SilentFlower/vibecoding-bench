Repair class access to cachedmethod when the original receiver parameter can be supplied by keyword.
Use the receiver's actual parameter name, which need not be self. Preserve positional and bound calls,
business arguments, instance isolation and info counters. A positional-only receiver must still reject
keyword binding. Missing and duplicate receivers must still raise TypeError. Do not change signatures,
dependencies, unrelated descriptors, pytest controls or global settings. Deliver meaningful public
regression tests in library/tests/test_cachedmethod.py that fail on the pinned original and pass after
the repair. Only library/src/cachetools/_descriptor.py and that public test file are authorized.
