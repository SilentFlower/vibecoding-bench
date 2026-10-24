# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bidict.records.to_records/from_records with explicit key/value codec callables, a schema1 ordered pairs format and checked codec identifier. Preserve tuple/int/str/None keys and values through caller-defined JSON-compatible encodings, reject malformed or duplicate-after-decoding keys/values instead of silently dropping rows, and allow the caller to explicitly choose ordered/frozen/custom result classes. Never import classes or execute expressions from data; preserve source relationships and callback errors.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bidict_o05_dev.py and concise English compatibility documentation at library/docs/development-bidict-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bidict/records.py
- library/tests/test_development_bidict_o05_dev.py
- library/docs/development-bidict-o05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
