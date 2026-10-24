# Engineering contract: SC-PRIORITY-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Job.set_priority(priority) accepting nonboolean integers, returning self. Scheduler.run_pending must order due jobs first by existing next_run, then descending explicit priority (default zero), then stable registration order for ties. Earlier due times always win over priority. Preserve due-set snapshot, CancelJob semantics, exception propagation, Job.__lt__, run_all order and behavior of unconfigured jobs.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sc_priority_dev.py and concise English compatibility documentation at library/docs/development-sc-priority-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/schedule/__init__.py
- library/development_tests/test_development_sc_priority_dev.py
- library/docs/development-sc-priority-dev.md
