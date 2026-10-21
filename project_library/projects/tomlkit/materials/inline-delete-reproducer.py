from tomlkit import dumps, parse

doc = parse('t = {a="", b.c=1, d=1}\n')
del doc["t"]["b"]["c"]
print(doc.unwrap())  # {"t": {"a": "", "b": {}, "d": 1}}
print(dumps(doc))  # invalid: t = {a="", , d=1}\n
only = parse("t = {b.c=1}\n")
del only["t"]["b"]["c"]
print(only.unwrap())  # {"t": {"b": {}}}
print(dumps(only))  # t = {}\n, silently loses the still-present b
