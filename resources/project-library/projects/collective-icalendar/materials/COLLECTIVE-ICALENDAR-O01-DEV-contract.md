# Engineering contract: COLLECTIVE-ICALENDAR-O01-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Repair cli.view to use Event.start/end/duration rather than deriving a separate zero-length default. An all-day DATE DTSTART with no DTEND/DURATION has the model-defined exclusive next-day end and one-day duration; timed events without end remain zero-length. Preserve explicit DTEND/DURATION, floating/aware display rules and model validation of illegal combinations. Do not hardcode dates or change the Event model to fit CLI output.

Deliver meaningful original-failing public regression tests at library/tests/test_development_collective_icalendar_o01_dev.py and concise English compatibility documentation at library/docs/development-collective-icalendar-o01-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/icalendar/cli.py
- library/tests/test_development_collective_icalendar_o01_dev.py
- library/docs/development-collective-icalendar-o01-dev.md
