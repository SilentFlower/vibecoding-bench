# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Expand explicit PyprojectTomlConfigSettingsSource Path with expanduser before resolve. A local ~/pyproject.toml must read exactly the same bytes/table as its absolute Path. Preserve ordinary relative/absolute paths, missing-file empty source, custom table header and current depth/cwd discovery; no cwd mutation or new search location. Unknown user expansion errors propagate clearly. Use synthetic HOME and temporary files only.

Deliver real implementation, original-failing public tests at library/tests/test_development_pydantic_settings_04_dev.py, and English compatibility documentation at library/docs/development-pydantic-settings-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pydantic_settings/sources/providers/pyproject.py
- library/tests/test_development_pydantic_settings_04_dev.py
- library/docs/development-pydantic-settings-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
