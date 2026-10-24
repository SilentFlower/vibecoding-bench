# Engineering contract: SC-INTERVAL-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Validate Job interval as a positive finite nonboolean int/float at construction and revalidate before _schedule_next_run, because existing public attributes can be mutated. Raise ScheduleValueError before registering a callback or entering the next-run advancement loop for zero/negative/nonfinite/invalid types. Keep positive fractional fixed intervals working and original integer random intervals; reject noninteger random bounds clearly rather than delegating them to randint. Preserve deadline, timezone and weekday logic.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sc_interval_dev.py and concise English compatibility documentation at library/docs/development-sc-interval-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/schedule/__init__.py
- library/development_tests/test_development_sc_interval_dev.py
- library/docs/development-sc-interval-dev.md
