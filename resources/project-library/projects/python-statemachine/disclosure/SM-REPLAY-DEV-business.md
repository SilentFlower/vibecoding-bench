# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement statemachine.replay.replay(factory,document,*,verify=True,max_records=10000) returning frozen ReplayResult(machine,results). Fully validate completed JSON journal before calling factory; never import a class name from data. Run each EventCall through completed MachineRunner on the new factory instance and preserve native callback execution. Verify before/after states and values plus passed/error status per index, reject divergence before next event; verify=False returns actual results explicitly. Handle empty journals and expected disallowed events. Do not mutate journal data or claim external callback side effects are rolled back.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sm_replay_dev.py and concise English compatibility documentation at library/docs/development-sm-replay-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/statemachine/replay.py
- library/development_tests/test_development_sm_replay_dev.py
- library/docs/development-sm-replay-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
