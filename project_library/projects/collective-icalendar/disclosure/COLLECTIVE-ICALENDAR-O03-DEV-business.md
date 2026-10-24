# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement icalendar.attendee_update.upsert_attendee/remove_attendee on real component/vCalAddress objects, returning isolated same-class copies. Match URI scheme case-insensitively and preserve the remaining URI exactly, update only supplied parameters (None removes), retain CN/ROLE/RSVP/delegation lists and unrelated attendees. Explicit duplicate error/all and strict missing-remove policies must work; reject malformed addresses, never modify the source or claim all URI parts are case-insensitive.

Deliver meaningful original-failing public regression tests at library/tests/test_development_collective_icalendar_o03_dev.py and concise English compatibility documentation at library/docs/development-collective-icalendar-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/icalendar/attendee_update.py
- library/tests/test_development_collective_icalendar_o03_dev.py
- library/docs/development-collective-icalendar-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
