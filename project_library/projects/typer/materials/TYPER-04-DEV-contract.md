# Engineering contract: TYPER-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add shop.py fulfill CATALOG ORDERS_JSON --output NEW_JSON. Orders is array of existing sku plus strict positive int quantity (bool forbidden); aggregate repeated sku in first-seen order, validate combined demand against real inventory before publishing one complete new catalog. Unknown sku/malformed line/underflow reject whole batch, no input mutation or partial output. Preserve catalog order and unaffected fields, empty batch explicitly copies catalog. Print structured aggregate fulfillment before/after receipt only after exclusive atomic publication; do not publish receipt on failure or silently fulfill partial demand. All earlier commands and original Typer remain.

Deliver real implementation, original-failing public tests at app/development_tests/test_development_typer_04_dev.py, and English compatibility documentation at app/docs/development-typer-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- app/inventory_fulfill.py
- app/development_tests/test_development_typer_04_dev.py
- app/docs/development-typer-04-dev.md
