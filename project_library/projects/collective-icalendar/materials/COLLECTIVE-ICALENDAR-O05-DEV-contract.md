# Engineering contract: COLLECTIVE-ICALENDAR-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement icalendar.schedule_shift.shift_schedule(calendar, delta, *, mode="wall", ambiguous="error", shift_absolute_alarms=False). Return a deep copy shifting VEVENT/VTODO DTSTART/DTEND/DUE/RECURRENCE-ID, RDATE/EXDATE periods and RRULE UNTIL consistently across masters/overrides, preserving UID/text/duration and leaving timezone definitions/metadata unchanged. Explicit wall-vs-UTC semantics must handle DST gaps/ambiguity, floating times and integral-day DATE precision. Relative alarms stay relative; absolute triggers move only on opt-in. Invalid inputs must not alter original objects.

Deliver meaningful original-failing public regression tests at library/tests/test_development_collective_icalendar_o05_dev.py and concise English compatibility documentation at library/docs/development-collective-icalendar-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/icalendar/schedule_shift.py
- library/tests/test_development_collective_icalendar_o05_dev.py
- library/docs/development-collective-icalendar-o05-dev.md
