# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair contrib.concurrent.ensure_lock with finally restoration covering lock creation/subtype selection, normal exit and body/worker exceptions. Preserve exact original lock identity and whether _lock was owned, inherited, absent or explicitly None; a temporary class lock must not leak after failure. Nested contexts restore each prior level and thread_map/process_map continue using the same actual context manager. Keep normal worker error propagation, do not acquire unrelated locks or claim transaction/concurrent class-mutation isolation. Acceptance uses local locks and a one-thread failing worker, never external services.

Deliver real implementation, original-failing public tests at library/tests/test_development_tqdm_05_dev.py, and English compatibility documentation at library/docs/development-tqdm-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/tqdm/contrib/concurrent.py
- library/tests/test_development_tqdm_05_dev.py
- library/docs/development-tqdm-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
