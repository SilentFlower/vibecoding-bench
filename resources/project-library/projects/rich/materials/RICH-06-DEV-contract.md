# Engineering contract: RICH-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Console._collect_renderables single-Text collection: retain the Text own justify/overflow/no_wrap/style/spans through a copy rather than recreating it from the separator template. Current print end replaces the copy end, explicit print justify/overflow/no_wrap still have their existing priority, and the caller Text never mutates. Preserve multiple-item separator-join policy, ordinary strings, non-text renderables/Group/Panel and style wrapping. Verify actual Console output for centered/right-aligned Unicode and ellipsis/no-wrap, not only intermediary attributes; do not change default multi-Text conflict semantics in this delivery.

Deliver real implementation, original-failing public tests at library/tests/test_development_rich_06_dev.py, and English compatibility documentation at library/docs/development-rich-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/rich/console.py
- library/tests/test_development_rich_06_dev.py
- library/docs/development-rich-06-dev.md
