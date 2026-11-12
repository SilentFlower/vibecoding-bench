# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Validate real IceCreamDebugger constructor/configureOutput declarations before mutating any field or auto-swapping builtin color output. Prefix must be text/callable, formatting/output callbacks callable, flags actual bool and lineWrapWidth positive non-bool int. Preserve Sentinel.absent, empty prefixes, valid callbacks and existing builtin noColor output swap rules. Never execute a prefix/formatter during validation or pretend to know its eventual return type; callback execution failures remain runtime failures. Invalid combinations, unknown kwargs or no-arg configure must leave all previous fields identical, including prefix and outputFunction.

Deliver meaningful original-failing public regression tests at library/tests/test_development_icecream_o04_dev.py and concise English compatibility documentation at library/docs/development-icecream-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/icecream/icecream.py
- library/tests/test_development_icecream_o04_dev.py
- library/docs/development-icecream-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
