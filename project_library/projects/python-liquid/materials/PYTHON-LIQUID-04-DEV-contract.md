# Engineering contract: PYTHON-LIQUID-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add liquid.record_rendering.render_records and async-generator render_records_async over lazy (id,Mapping) records, returning immutable RenderedRecord(id,status,output,error-type). Use real BoundTemplate.render/render_async each time so assigns/cycle state does not leak across records. Preserve input order and identity; reject duplicate ids; continue mode records LiquidError without data/error-message leakage, fail-fast rethrows. Ordinary user exceptions and cancellation propagate. Keep work strictly pull-driven with no prefetch/unbounded tasks; closing after one item never executes later records. Both APIs are serial by explicit contract, no concurrency claim.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_liquid_04_dev.py, and English compatibility documentation at library/docs/development-python-liquid-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/liquid/record_rendering.py
- library/tests/test_development_python_liquid_04_dev.py
- library/docs/development-python-liquid-04-dev.md
