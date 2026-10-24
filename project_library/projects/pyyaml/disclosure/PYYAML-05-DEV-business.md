# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add yaml.limits.LimitedSafeLoader/load_limited for decoded str single-document input only. Optional strict nonnegative integer max_chars, max_nodes (nonalias nodes), max_depth (root=1, keys count), max_aliases (reference occurrences). Check text length before parse and node/depth/alias budgets before compose; marked ComposerError for node constraints, YAMLError for text budget. Preserve normal safe graph identity and finally dispose, empty document zero budgets legal. No byte/stream budget claim, no large exhaustion payloads, no changes to default loader limits.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyyaml_05_dev.py, and English compatibility documentation at library/docs/development-pyyaml-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/lib/yaml/limits.py
- library/tests/test_development_pyyaml_05_dev.py
- library/docs/development-pyyaml-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
