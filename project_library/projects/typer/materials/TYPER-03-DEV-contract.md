# Engineering contract: TYPER-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add real shop.py adjust SOURCE --sku SKU --delta SIGNED_INT --output NEW_JSON using delivered validated inventory store. Apply delta exactly once to existing unique sku, permit positive/negative/zero changes, reject underflow and unknown sku before any write. Preserve product order/name/other quantities and all input bytes. Publish complete new canonical catalog with original exclusive atomic-output policy, print structured sku/before/delta/after receipt only after success; invalid inputs/existing outputs nonzero without partial result. Keep product/export/import-csv and original Typer source/environment.

Deliver real implementation, original-failing public tests at app/development_tests/test_development_typer_03_dev.py, and English compatibility documentation at app/docs/development-typer-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- app/inventory_adjust.py
- app/development_tests/test_development_typer_03_dev.py
- app/docs/development-typer-03-dev.md
