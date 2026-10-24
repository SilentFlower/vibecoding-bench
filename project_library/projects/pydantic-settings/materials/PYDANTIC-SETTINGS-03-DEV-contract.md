# Engineering contract: PYDANTIC-SETTINGS-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend existing _serialize_value container handling to frozenset and collections.deque using existing pydantic_core.to_jsonable_python before JSON encoding. Real CliApp.serialize/run roundtrip must preserve values and model container types; deque order and duplicates remain, frozenset order is not promised. Complete JSON-array arguments for these two containers must decode JSON escapes exactly once, including Unicode, quotes, newlines and backslashes, retaining the existing numeric-string coercion. Cover empty containers replacing nonempty defaults, commas and enum members. Existing shorthand input, NoDecode, list/dict/set/tuple and scalar policies remain.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydantic_settings_03_dev.py, and English compatibility documentation at library/docs/development-pydantic-settings-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pydantic_settings/sources/providers/cli.py
- library/tests/test_development_pydantic_settings_03_dev.py
- library/docs/development-pydantic-settings-03-dev.md
