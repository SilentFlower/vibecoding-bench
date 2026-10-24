# Engineering contract: PYDANTIC-SETTINGS-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair EnvSettingsSource.next_field to resolve TypeAliasType, parameterized named aliases and outer Annotated wrappers before inspecting Union/model/dataclass/dict structure. Optional named model aliases must decode nested list fields like direct models, preserving None and whole-object JSON. Follow alias layers without unbounded traversal into recursive model fields; inspect actual provided path only. Preserve field validation metadata, case policy, generic substitutions, invalid input rejection and existing plain/Union handling. Do not remove model aliases or globally force JSON parsing.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydantic_settings_06_dev.py, and English compatibility documentation at library/docs/development-pydantic-settings-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pydantic_settings/sources/providers/env.py
- library/tests/test_development_pydantic_settings_06_dev.py
- library/docs/development-pydantic-settings-06-dev.md
