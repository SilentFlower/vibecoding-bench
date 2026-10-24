# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair SafeConstructor.flatten_mapping merge deduplication using constructed hashable YAML key semantics, not id(key_node.value) or raw spelling. Earlier sources in merge sequence win, local explicit keys still override, nested/single/multiple merge and semantically equal scalar keys (01/1, bool/int under existing Python mapping semantics) consistent. Invalid unhashable keys must raise marked ConstructorError. Preserve default YAML1.1 typing and original merge-node behavior; no arbitrary object equality policy change.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyyaml_01_dev.py, and English compatibility documentation at library/docs/development-pyyaml-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/lib/yaml/constructor.py
- library/tests/test_development_pyyaml_01_dev.py
- library/docs/development-pyyaml-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
