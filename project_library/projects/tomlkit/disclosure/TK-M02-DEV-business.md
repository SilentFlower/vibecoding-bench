# Business scope

Fix inline-table rendering after deleting the last leaf of a dotted child. Deleting the leaf must retain every still-present parent as an explicit empty inline table at the correct path, and the result must parse to the independently expected logical tree. Preserve ordinary flat-key deletion output, untouched documents, sibling values, ordering, and existing dotted-child insertion. Keep the change limited to the allowed paths and add regression coverage.

# Investigation topics

- Determine why deleting the final child field of an inline table produces two commas or removes an empty parent table.

# Supplied business material: materials/inline-delete-reproducer.py

from tomlkit import dumps, parse

doc = parse('t = {a="", b.c=1, d=1}\n')
del doc["t"]["b"]["c"]
print(doc.unwrap())  # {"t": {"a": "", "b": {}, "d": 1}}
print(dumps(doc))  # invalid: t = {a="", , d=1}\n
only = parse("t = {b.c=1}\n")
del only["t"]["b"]["c"]
print(only.unwrap())  # {"t": {"b": {}}}
print(dumps(only))  # t = {}\n, silently loses the still-present b


# Supplied business material: materials/inline-repair.md

# Inline dotted leaf deletion contract

Deleting the last leaf does not delete its still-present parent. Render explicit empty inline tables at the correct path, including nested and quoted dotted paths. Preserve sibling values and ordering; the rendered tree must equal an independently specified expected tree, not merely the candidate unwrap. Protect ordinary flat-key deletion exact output, untouched round trips, existing dotted insertion and explicit parent deletion. Do not rebuild whole documents through dict/unwrap or change Container deletion semantics. Authorized source and public test changes only, with meaningful regression tests. This independent scene does not inherit the Array repair.

