# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add Component.from_ical_strict(st, multiple=False), inherited by Calendar and LazyCalendar, as an explicit strict component-boundary parsing API. Before constructing any parser/model or caching any timezone, inspect all unfolded BEGIN/END markers with a textual stack: reject orphan END, case-insensitive name mismatch, cross-layer closure, and unfinished BEGIN at EOF. Include actual and expected names in mismatch errors. Accept str, bytes and Path (read once), valid nested and unknown X components, and preserve the multiple return contract plus subclass parser dispatch. Use a shared private ComponentIcalParser boundary validator and then the existing cls.from_ical path. This checks structural component boundaries, not every RFC property. Preserve the original from_ical signature and permissive behavior, all frozen tests, custom factories and lazy parsing; do not hardcode old malformed fixtures or make strictness the default.

Deliver meaningful original-failing public regression tests at library/tests/test_development_collective_icalendar_o02_dev.py and concise English compatibility documentation at library/docs/development-collective-icalendar-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/icalendar/parser/ical/component.py
- library/src/icalendar/cal/component.py
- library/tests/test_development_collective_icalendar_o02_dev.py
- library/docs/development-collective-icalendar-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
