# Engineering contract: PACKAGING-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add Requirement.applies(selected_extras=(),environment=None). Evaluate singular standard extra for each selected normalized name and return any match, binding the same extra throughout the whole marker; empty selection uses extra="" once. Markerless requirements always apply. Selected consumer extras are separate from Requirement.extras (requested dependency features). Copy environment, chosen extra takes priority, preserve existing Marker evaluation and set-valued lock_file extras semantics. Validate iterable names and reject a bare string or non-string name; do not mutate inputs.

Deliver real implementation, original-failing public tests at library/tests/test_development_packaging_03_dev.py, and English compatibility documentation at library/docs/development-packaging-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/packaging/requirements.py
- library/tests/test_development_packaging_03_dev.py
- library/docs/development-packaging-03-dev.md
