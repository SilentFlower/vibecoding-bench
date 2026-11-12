# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair tqdm_asyncio.as_completed to infer total only when len(fs) is supported. Accept standard asyncio.as_completed task generators under the pinned Python runtime, consume once through the real standard-library scheduler, use unknown total otherwise and preserve explicit total, empty input, timeout/cancellation/task errors and gather result-order behavior. Do not list() tasks solely to obtain a total or swallow non-TypeError length failures. All acceptance tasks use local asyncio.sleep(0), not network services or real accounts.

Deliver real implementation, original-failing public tests at library/tests/test_development_tqdm_04_dev.py, and English compatibility documentation at library/docs/development-tqdm-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/tqdm/asyncio.py
- library/tests/test_development_tqdm_04_dev.py
- library/docs/development-tqdm-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
