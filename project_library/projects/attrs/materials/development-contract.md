# Identity-scoped Attribute filters

Two unrelated attrs classes may expose content-equal Attribute objects. Selecting one Attribute in include/exclude must match that exact object only. Do not change Attribute equality or hashing globally.

* include(A.x) must include the exact A.x and reject an equal-but-distinct B.x; exclude is its logical complement. A copied/evolved Attribute is distinct too.
* Supplying include(A.x, B.x) or exclude(A.x, B.x) must select both exact objects, even when they compare equal; a third equal object stays unselected. Duplicate arguments are harmless.
* String field names still match across classes. Type arguments retain the current exact value.__class__ behavior, not isinstance behavior. Mixed arguments use the existing OR semantics; empty filters retain their existing behavior.
* Inheritance follows actual field object identity: if the inherited field object is shared, it is selected; a newly generated distinct Attribute is not. attrs.asdict/astuple and attr.asdict/astuple must use the same rule.
* Keep _split_what's existing frozenset return contract and Attribute equality/hash unchanged. Preserve frozen tests and add no dependencies or test configuration.

Modify only `library/src/attr/filters.py` and add original-failing public tests at `library/tests/test_development_filter_identity.py`.
