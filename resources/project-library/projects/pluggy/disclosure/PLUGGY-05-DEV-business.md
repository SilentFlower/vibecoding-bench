# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pluggy.scoped.temporary_plugins(manager,[(name,plugin),...]) context manager. Preflight all names/identities/blocked/existing conflicts before registration, preserve declared order and existing plugins, then remove only still-registered identical owned objects in reverse order on success/body error/partial historic registration failure. Respect manager-returned actual names via identity lookup, keep nested scopes independent and never remove an unrelated replacement subsequently installed under the same name. Reuse earlier identity repair for eq-equal/unhashable plugins. Roll back registrations/hooks/distribution associations via actual unregister semantics, not arbitrary external callback effects or all newly declared hookspecs.

Deliver real implementation, original-failing public tests at library/tests/test_development_pluggy_05_dev.py, and English compatibility documentation at library/docs/development-pluggy-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pluggy/scoped.py
- library/tests/test_development_pluggy_05_dev.py
- library/docs/development-pluggy-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
