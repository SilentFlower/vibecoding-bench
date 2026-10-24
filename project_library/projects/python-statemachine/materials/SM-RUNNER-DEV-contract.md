# Engineering contract: SM-RUNNER-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement statemachine.runner.EventCall, EventResult, normalize_call and MachineRunner(machine) with dispatch(call,*,index=0,errors="raise") and run(calls,*,errors="raise"). Invoke actual send with detached positional/keyword callback arguments; reject empty calls and delay/send_id/internal controls in immediate batches. Reuse completed snapshots before/after actual execution, retain real callback result, collect only TransitionNotAllowed as error records and continue when requested. Programming/callback/source exceptions propagate. Stay lazy and sequential, preserve original native transition semantics and do not claim rollback of external callback side effects; async uses separate runner.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sm_runner_dev.py and concise English compatibility documentation at library/docs/development-sm-runner-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/statemachine/runner.py
- library/development_tests/test_development_sm_runner_dev.py
- library/docs/development-sm-runner-dev.md
