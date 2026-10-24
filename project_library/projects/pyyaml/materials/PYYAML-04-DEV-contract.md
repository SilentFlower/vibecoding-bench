# Engineering contract: PYYAML-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add yaml.tagged TaggedValue plus PreservingLoader/Dumper and load_preserving/dump_preserving. Unknown scalar keeps exact scalar text, unknown sequence/mapping safely constructs contents; preserve tag and node kind, recursive/shared alias identity via generator construction and representer. Unknown Python object/apply tags remain inert TaggedValue, never import/call targets. Existing known SafeLoader typing/default unknown-tag rejection unchanged; complex tagged keys with unhashable payload remain unsupported safe key errors. No global class registration changes.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyyaml_04_dev.py, and English compatibility documentation at library/docs/development-pyyaml-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/lib/yaml/tagged.py
- library/tests/test_development_pyyaml_04_dev.py
- library/docs/development-pyyaml-04-dev.md
