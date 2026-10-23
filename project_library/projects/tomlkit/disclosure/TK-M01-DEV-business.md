# Business scope

Fix in-place repetition for Array in the supplied reproducer. The same Array object must remain bound to the document, and its values, index operations, unwrap, and serialized TOML must agree after valid repetition counts. Follow Python list index-count semantics, preserve exact text for *= 1, and retain existing comments and the behavior of unrelated array operations. Changes to formatting may be local to material newly added or cleared by repetition. Include regression tests within the allowed paths.

# Investigation topics

- 配置数组乘二后内存是四项，为什么写出来还是两项？

# Supplied business material: materials/array-reproducer.py

from tomlkit import dumps, parse

doc = parse("a = [1, 2]\n")
a = doc["a"]
a *= 2
print(a.unwrap())  # [1, 2, 1, 2]
print(dumps(doc))  # a = [1, 2]\n


# Supplied business material: materials/array-repair.md

# In-place Array repetition contract

Fix Array only. Keep the same object bound to its document. Values, unwrap, indexing and serialized TOML must agree after counts 0, negative, 1, 2, 3, booleans and valid __index__ objects. Invalid non-index counts raise TypeError before any change. Count 1 preserves exact bytes. Count <=0 clears contents but retains the outer key and trailing comment. Count >1 retains existing comments and renders valid TOML; added material may use local formatting. Repeated mutable elements follow Python list reference semantics. Empty arrays and later append, replace and delete must remain consistent. Inputs are finite, acyclic and legally representable. Do not alter AoT or numeric multiplication. Add meaningful tests within the authorized test path. Each modify entry starts independently from the original checkout.

