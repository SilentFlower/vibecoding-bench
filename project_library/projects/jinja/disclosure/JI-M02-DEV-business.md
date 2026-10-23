# Business scope

Fix the demonstrated urlencode dispatch bug so standard Mapping implementations are encoded as their items. Preserve dict behavior, duplicate keys in pair iterables and existing string-path quoting. Limit changes to the allowed paths and deliver meaningful public regression tests.

Fix map(attribute="field", default=none) so missing fields produce the explicit None default. Omitting default must retain Undefined; existing None, False, 0 and empty-string values must remain unchanged. Cover synchronous and asynchronous templates, deliver public regression tests and preserve the previously accepted Mapping urlencode behavior.

# Investigation topics

- 解释 UserDict 查询值变成键字符的分派错误

# Supplied business material: materials/S03/urlencode.md

# Mapping query encoding
Pinned source reproduction:
from collections import UserDict
from jinja2.filters import do_urlencode
do_urlencode({'Aa': 'A+1'}) == 'Aa=A%2B1'
do_urlencode(UserDict({'Aa': 'A+1'})) == 'A=a'
A UserDict with the one-character key 'q' raises ValueError. Pair iterables may have duplicate keys, and string inputs represent paths whose slash quoting behavior must stay unchanged. The diagnosis concerns this frozen original reproduction even if later tasks accept code changes.


# Supplied business material: materials/S03/repair-boundaries.md

# Repair contract
Modify only library/src/jinja2/filters.py, library/tests/test_filters.py, and library/tests/test_async_filters.py. Include regression tests. Do not change dependencies, test configuration, the runner, unrelated APIs, string-path quoting, pair-iterable ordering or duplicate keys. Native acceptance uses independent tests and the frozen full upstream collection; editing public tests cannot replace that collection.


# Supplied business material: materials/S03/map-default.md

# Explicit None map default
rows=[{}, {'field': None}, {'field': False}, {'field': 0}, {'field': ''}]
Compare rows|map(attribute='field', default=none)|list with rows|map(attribute='field')|list. The pinned original returns Undefined for the first item in both expressions. The explicit None default must instead return None; omission must retain Undefined, and existing values retain type and value.
Exercise synchronous and asynchronous environments, nested attributes and StrictUndefined, and preserve existing shared-getter users. Preserve the previously accepted Mapping urlencode behavior. Deliver meaningful public regression tests in the authorized files; tests are part of the requested change.

