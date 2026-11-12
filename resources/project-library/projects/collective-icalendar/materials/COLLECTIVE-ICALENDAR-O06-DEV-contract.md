# Engineering contract: COLLECTIVE-ICALENDAR-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement icalendar.fingerprint.calendar_fingerprint with declared schema/profile/algorithm/ignore fields. Canonicalize via actual sorted property/parameter serialization plus order-independent child-component multisets, preserving duplicates, DATE-vs-floating-vs-aware values, unknown extensions and repeated-property value order. Default include all fields; allow only explicit DTSTAMP/CREATED/LAST-MODIFIED omission, reject unsupported profiles/depth budgets and business-field omission. Same permitted folding/property/component reorder must hash equally, real summary/start/extension changes differently, and input objects must remain unchanged. Do not claim a bare hash of existing sorted serialization is a new semantic profile.

Deliver meaningful original-failing public regression tests at library/tests/test_development_collective_icalendar_o06_dev.py and concise English compatibility documentation at library/docs/development-collective-icalendar-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/icalendar/fingerprint.py
- library/tests/test_development_collective_icalendar_o06_dev.py
- library/docs/development-collective-icalendar-o06-dev.md
