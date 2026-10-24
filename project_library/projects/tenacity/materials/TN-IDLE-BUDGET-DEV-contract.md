# Engineering contract: TN-IDLE-BUDGET-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add tenacity.stop.stop_before_idle_budget(budget) as stop_base. Accept nonnegative finite seconds or timedelta, rejecting booleans/nonfinite/negative values. Stop when retry_state.idle_for + upcoming_sleep is greater than or equal to budget, before that next sleep is issued. Count only retry waiting, not target execution elapsed time; a zero budget stops after the first rejected attempt even for zero wait. Integrate with actual Retrying and AsyncRetrying and stop_any/stop_all without storing mutable per-call counters in the shared policy. Preserve other stop and wait semantics.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tn_idle_budget_dev.py and concise English compatibility documentation at library/docs/development-tn-idle-budget-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tenacity/stop.py
- library/development_tests/test_development_tn_idle_budget_dev.py
- library/docs/development-tn-idle-budget-dev.md
