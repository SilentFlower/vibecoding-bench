# Business scope

Implement only the explicitly authorized recursive comparator repair and public regressions. Preserve every listed compatibility boundary and all frozen original tests.

# Investigation topics



# Supplied business material: materials/equality-repair.md

Explicit repair authorization: modify only library/jmespath/visitor.py and add app/test_json_equality.py. For JSON data {a:[true],b:[1]}, a==b currently returns true; nested objects have the same Boolean/number confusion. Required == and != recursively preserve JSON Boolean types inside arrays/objects, in either operand order and filter expressions. Preserve numeric1==1.0, scalar Boolean/number separation, nulls, array order/length and object key sets independent of key order. Inputs remain unchanged. Scope is comparator equality on ordinary acyclic JSON values; do not change contains, ordering, custom-function APIs or non-JSON extension semantics. Preserve every original test/config and add meaningful public unittest regressions failing on original and passing after repair. The official equality specification is https://jmespath.org/specification.html#equality-operators .

