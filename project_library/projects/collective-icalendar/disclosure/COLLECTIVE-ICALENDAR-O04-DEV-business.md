# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement icalendar.todo_transition.transition_todo for actual Todo objects with complete/reopen/cancel actions, returning an isolated same-class copy. Completion requires an explicit aware timestamp normalized to UTC and 100 percent; reopen clears COMPLETED and uses 0..99 progress/NEEDS-ACTION or IN-PROCESS; cancel clears completion and uses CANCELLED/zero. Validate progress and timestamps before publication, preserve UID/start/due and by-default SEQUENCE/DTSTAMP, offer explicit sequence bump/stamp, and never read a wall clock or send invitations.

Deliver meaningful original-failing public regression tests at library/tests/test_development_collective_icalendar_o04_dev.py and concise English compatibility documentation at library/docs/development-collective-icalendar-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/icalendar/todo_transition.py
- library/tests/test_development_collective_icalendar_o04_dev.py
- library/docs/development-collective-icalendar-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
