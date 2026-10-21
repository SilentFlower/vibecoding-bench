from boltons.iterutils import remap, get_path

record = {"line": {"empty": None, "count": 0, "enabled": False, "label": ""}, "notes": [None, "coffee"]}
cleaned = remap(record, visit=lambda path, key, value: value is not None)
print(record)
print(cleaned)
sentinel = object()
print(get_path(record, ("line", "empty"), default=sentinel) is None)
print(get_path(record, ("line", "absent"), default=sentinel) is sentinel)
