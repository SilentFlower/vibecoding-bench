# Engineering contract: CERBERUS-O03-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add actual compare_to rule with schema-validated {field, operator, missing} using only lt/le/eq/ne/ge/gt. Resolve existing sibling/dotted/root ^ paths through the real lookup protocol after normalization, distinguish missing targets from existing None, default missing to error or explicitly ignore, and report failed/incomparable comparisons in native field error trees. Reject unknown operators at schema validation, never eval strings or alter dependencies/min/max semantics.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cerberus_o03_dev.py and concise English compatibility documentation at library/docs/development-cerberus-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cerberus/validator.py
- library/tests/test_development_cerberus_o03_dev.py
- library/docs/development-cerberus-o03-dev.md
