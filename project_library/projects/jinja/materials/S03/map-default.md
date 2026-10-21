# Explicit None map default
rows=[{}, {'field': None}, {'field': False}, {'field': 0}, {'field': ''}]
Compare rows|map(attribute='field', default=none)|list with rows|map(attribute='field')|list. The pinned original returns Undefined for the first item in both expressions. The explicit None default must instead return None; omission must retain Undefined, and existing values retain type and value.
Exercise synchronous and asynchronous environments, nested attributes and StrictUndefined, and preserve existing shared-getter users. Preserve the previously accepted Mapping urlencode behavior. Deliver meaningful public regression tests in the authorized files; tests are part of the requested change.
