from tomlkit import dumps, parse

doc = parse("a = [1, 2]\n")
a = doc["a"]
a *= 2
print(a.unwrap())  # [1, 2, 1, 2]
print(dumps(doc))  # a = [1, 2]\n
