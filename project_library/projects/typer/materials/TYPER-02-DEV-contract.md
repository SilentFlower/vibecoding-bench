# Engineering contract: TYPER-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend the already delivered app/shop.py product/export application with real import-csv SOURCE --output NEW_JSON. Require exactly sku/name/quantity CSV headers in any order; UTF8/BOM, normal CSV quoted commas/newlines and Unicode supported, integer ASCII nonnegative quantity and unique nonempty sku/name. Validate all rows before publishing canonical three-field JSON in input order; header-only emits []. Preserve original input, refuse existing/symlink/same-path output, use same-directory completed temp+exclusive link so no partial/overwrite race. Add reusable app/inventory_store.py and command-module registration to support subsequent real business commands without replacing delivered product/export. Do not modify Typer library or dependency environment.

Deliver real implementation, original-failing public tests at app/development_tests/test_development_typer_02_dev.py, and English compatibility documentation at app/docs/development-typer-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- app/shop.py
- app/inventory_store.py
- app/inventory_import.py
- app/development_tests/test_development_typer_02_dev.py
- app/docs/development-typer-02-dev.md
