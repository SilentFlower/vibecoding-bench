# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair MarkupMachine exported global after_state_change to use actual after list, not before list. Preserve callback representation, order, empty/after-only/before-only behavior and hierarchical/code-generation consumers of markup. Demonstrate a real exported then reconstructed order machine executes distinct before and after exactly once, not merely string equality. Existing markup/model binding and callback execution remain unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_transitions_01_dev.py, and English compatibility documentation at library/docs/development-transitions-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/transitions/extensions/markup.py
- library/tests/test_development_transitions_01_dev.py
- library/docs/development-transitions-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
