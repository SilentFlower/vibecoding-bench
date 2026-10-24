# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement alive_progress.weighted.alive_weighted_it(source,weight,*,total=None,finalize=None,**bar_options). Use real alive_bar and snapshots; evaluate weight exactly once per consumed item before yielding, require nonnegative nonboolean integer (zero allowed), and acknowledge that weight only when iteration resumes. Keep item identity/order and explicit total-work units, without inspecting or summing the whole source. Falsey weight/finalizer callables work; only normal exhaustion finalizes once, not early close or source/weight failure. Reject manual mode and preserve original alive_it.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ap_weighted_dev.py and concise English compatibility documentation at library/docs/development-ap-weighted-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/alive_progress/weighted.py
- library/development_tests/test_development_ap_weighted_dev.py
- library/docs/development-ap-weighted-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
