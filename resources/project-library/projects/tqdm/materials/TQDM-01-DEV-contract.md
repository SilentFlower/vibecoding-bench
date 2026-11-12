# Engineering contract: TQDM-01-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair tqdm.contrib.itertools.product repeat handling via operator.index before computing totals or delegating to itertools.product. Preserve Python arbitrary-precision exponent totals for numpy integer repeats and custom __index__ objects, standard zero/negative/nonintegral behavior, yielded combinations and explicit total precedence. Do not preconsume unknown-length inputs to infer total; total remains None where lengths are unavailable. Test actual product generation and wrapper-observed totals without enumerating astronomically large products. Preserve other combinator wrappers.

Deliver real implementation, original-failing public tests at library/tests/test_development_tqdm_01_dev.py, and English compatibility documentation at library/docs/development-tqdm-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/tqdm/contrib/itertools.py
- library/tests/test_development_tqdm_01_dev.py
- library/docs/development-tqdm-01-dev.md
