# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add real shop.py low-stock CATALOG --threshold NONNEGATIVE_INT --output NEW_CSV. Validate catalog first, include quantity zero and exact threshold, stable ascending quantity order with original-order ties. CSV header sku/name/quantity always present including empty selection; Unicode, commas, quotes and multiline names preserve csv roundtrip. Publish new report with exclusive atomic output helper, preserve input bytes and existing reports, reject negative threshold/bad catalog. Print selected count/total selected quantity/threshold only after success. Keep all prior inventory/product/export commands and fixed Typer unchanged; report is a real generated application artifact, not advice or documentation.

Deliver real implementation, original-failing public tests at app/development_tests/test_development_typer_06_dev.py, and English compatibility documentation at app/docs/development-typer-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- app/inventory_report.py
- app/development_tests/test_development_typer_06_dev.py
- app/docs/development-typer-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
