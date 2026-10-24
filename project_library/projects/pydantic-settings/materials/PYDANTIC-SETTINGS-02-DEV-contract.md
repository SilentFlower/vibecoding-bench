# Engineering contract: PYDANTIC-SETTINGS-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair _CliArg.dest so a validation_alias only strips the CLI/env prefix when alias validation is actually enabled. With cli_prefix and validate_by_alias=False, --app.apple must update apple even when Field(alias=...) or validation_alias exists. Preserve normal alias validation, plain fields, no-prefix behavior, nested prefix and kebab-case. Disabled aliases remain rejected; do not enable alias validation or accept both names to mask loss.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydantic_settings_02_dev.py, and English compatibility documentation at library/docs/development-pydantic-settings-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pydantic_settings/sources/providers/cli.py
- library/tests/test_development_pydantic_settings_02_dev.py
- library/docs/development-pydantic-settings-02-dev.md
