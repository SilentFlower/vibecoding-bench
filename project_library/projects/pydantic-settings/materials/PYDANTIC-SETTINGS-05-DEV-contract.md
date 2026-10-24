# Engineering contract: PYDANTIC-SETTINGS-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair CliApp serialization to keep each CliUnknownArgs sequence at its own command level: after known optional/positional arguments of that level and before its selected subcommand. Do not hoist child unknowns into the root trailing sequence. Real parse/serialize/parse must preserve each parent/child unknown list, duplicates, known values and multi-level ownership. Existing no-subcommand and leaf end-of-options behavior remain; do not manufacture impossible parent end-marker+selected-child states.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydantic_settings_05_dev.py, and English compatibility documentation at library/docs/development-pydantic-settings-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pydantic_settings/sources/providers/cli.py
- library/tests/test_development_pydantic_settings_05_dev.py
- library/docs/development-pydantic-settings-05-dev.md
