# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Job.on_weekdays(*weekdays) for every(1).day(s) jobs, accepting nonempty integer weekdays 0..6 (Monday=0), deduplicating them and returning self. Integrate selection into _schedule_next_run in its configured timezone before existing UTC correction, preserving .at clock and strict-future scheduling. Revalidate eligibility if job attributes change; reject other intervals/units/start_day and invalid weekday values. Do not alter legacy .monday/.weeks or unconstrained daily schedules.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sc_weekdays_dev.py and concise English compatibility documentation at library/docs/development-sc-weekdays-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/schedule/__init__.py
- library/development_tests/test_development_sc_weekdays_dev.py
- library/docs/development-sc-weekdays-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
