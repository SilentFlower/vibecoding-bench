# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pluggy.discovery EntryPointCandidate/DiscoveryReport, discover_entrypoints(group,name=None) and load_entrypoint(manager,candidate). Discovery reads actual metadata fields and reports per-distribution metadata errors separately, never ep.load or plugin execution. Explicit loading re-reads group/name/value/distribution/version, requires exactly one complete matching candidate and no metadata errors, rejects stale/ambiguous inventory before import, and loads only the selected entry. Existing/blocked names return None without import. Commit through the earlier register_entrypoint verified path so rejected/None/renamed plugins never corrupt dist associations. Preserve default existing load API, and do not claim metadata preview proves runtime behavior safe.

Deliver real implementation, original-failing public tests at library/tests/test_development_pluggy_06_dev.py, and English compatibility documentation at library/docs/development-pluggy-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pluggy/discovery.py
- library/tests/test_development_pluggy_06_dev.py
- library/docs/development-pluggy-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
