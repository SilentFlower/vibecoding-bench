# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair default CheckedPMap key/value serializers and checked sequence default serializers to pass the actual format argument into nested CheckedType.serialize(format). A record field serializer must observe the same format whether direct, in a map, in a vector/set or through multiple levels. Preserve explicit __serializer__ authority and default format=None output; do not override caller policy, mutate records or claim arbitrary serialized dictionary keys become hashable. Incompatible key serialization remains an explicit normal error. Test actual nested values and custom serializers, not only mocked forwarding.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyrsistent_04_dev.py, and English compatibility documentation at library/docs/development-pyrsistent-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyrsistent/_checked_types.py
- library/tests/test_development_pyrsistent_04_dev.py
- library/docs/development-pyrsistent-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
