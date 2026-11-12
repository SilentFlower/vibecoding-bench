# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair entry-point loading to count and associate a distribution only after register actually returns the real registered plugin name. Introduce register_entrypoint(plugin,name,distribution) for the same verified commit path, supporting a subclass renaming or rejecting registration and the existing None-plugin policy. Never record an unloaded/rejected/blocked name, fabricate success from an unrelated already-registered object, or leave list_plugin_distributions raising KeyError. Preserve success order, metadata identity, existing load exceptions and normal unregister distribution cleanup. Tests patch metadata with local synthetic entry points, no actual discovery imports/network.

Deliver real implementation, original-failing public tests at library/tests/test_development_pluggy_02_dev.py, and English compatibility documentation at library/docs/development-pluggy-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pluggy/_manager.py
- library/tests/test_development_pluggy_02_dev.py
- library/docs/development-pluggy-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
