# Engineering contract: SM-ASYNC-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement statemachine.async_runner.AsyncMachineRunner using completed EventCall validation, EventResult and snapshots. dispatch awaits actual activate_initial_state and send only when awaitable, records actual completed states/results and supports normal sync machines. run accepts sync or async event sources, stays lazy, awaits one event before reading the next, stable indices and collect only TransitionNotAllowed. Propagate cancellation, callback and source errors. No nested asyncio.run, hidden threads, tasks or no-op guard shortcuts; preserve actual lifecycle and callback parameter isolation.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sm_async_dev.py and concise English compatibility documentation at library/docs/development-sm-async-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/statemachine/async_runner.py
- library/development_tests/test_development_sm_async_dev.py
- library/docs/development-sm-async-dev.md
