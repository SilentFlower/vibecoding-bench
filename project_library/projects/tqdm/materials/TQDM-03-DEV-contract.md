# Engineering contract: TQDM-03-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair CallbackIOWrapper write reporting: call the actual stream first, use a valid integer-index result as successful count, including zero and short writes, then invoke callback exactly once and return the unchanged original result. Binary buffer capacity uses memoryview.nbytes, text capacity uses character len. Reject bool/non-index/negative/over-capacity returned counts without progress callback; None retains explicitly documented legacy len(data) fallback. A stream write error never advances progress and the wrapper never retries short writes or closes/rewinds caller streams. Preserve the existing read reporting path.

Deliver real implementation, original-failing public tests at library/tests/test_development_tqdm_03_dev.py, and English compatibility documentation at library/docs/development-tqdm-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/tqdm/utils.py
- library/tests/test_development_tqdm_03_dev.py
- library/docs/development-tqdm-03-dev.md
