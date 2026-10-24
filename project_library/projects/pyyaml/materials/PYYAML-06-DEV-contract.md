# Engineering contract: PYYAML-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add yaml.marked.load_with_marks returning (ordinary SafeLoader value, tuple-path->immutable SourceSpan(start,end,line,column)). Zero-based CHARACTER offsets/line/column, root path (), mapping actual constructed keys and list indices. Use same composed node graph as actual construction, including flattened merge value origin, explicit override, alias multiple paths and finite recursive alias metadata. Do not wrap/change str/int/list/dict values, guess byte offsets, retain full Mark buffer in side table or silently load multiple documents. Empty returns (None,{}).

Deliver real implementation, original-failing public tests at library/tests/test_development_pyyaml_06_dev.py, and English compatibility documentation at library/docs/development-pyyaml-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/lib/yaml/marked.py
- library/tests/test_development_pyyaml_06_dev.py
- library/docs/development-pyyaml-06-dev.md
