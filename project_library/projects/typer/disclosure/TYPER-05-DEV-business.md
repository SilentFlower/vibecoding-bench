# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add shop.py reconcile CATALOG COUNTS_JSON --output NEW_JSON for a real physical-count reconciliation. Each existing sku appears at most once with strict nonnegative integer absolute quantity; reject duplicate/unknown/negative/bool/malformed records for whole batch. Uncounted items remain unchanged, counted zero is real zero, same value creates no difference. Preserve catalog order/names/input bytes, atomically publish complete new canonical catalog using delivered exclusive output policy. Print counted/changed and exact sku/before/after/delta differences only after success. This differs from delta adjustment/order fulfillment by explicit absolute-count semantics.

Deliver real implementation, original-failing public tests at app/development_tests/test_development_typer_05_dev.py, and English compatibility documentation at app/docs/development-typer-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- app/inventory_reconcile.py
- app/development_tests/test_development_typer_05_dev.py
- app/docs/development-typer-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
