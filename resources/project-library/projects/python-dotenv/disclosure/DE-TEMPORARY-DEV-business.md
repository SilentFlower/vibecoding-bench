# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement dotenv.environment.temporary_environment(values, *, override=False, remove_none=False) as a context manager. Validate the whole string/None mapping and environment key restrictions before any write. Apply only eligible keys, yield the tuple of changed keys, and restore exactly their pre-entry values or absence on normal/exceptional exit. Preserve unrelated changes inside the block and support nested contexts. None is ignored unless remove_none is explicit; existing keys require override. Do not claim thread isolation or mutate mapping inputs or permanent load_dotenv behavior.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_de_temporary_dev.py and concise English compatibility documentation at library/docs/development-de-temporary-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/dotenv/environment.py
- library/development_tests/test_development_de_temporary_dev.py
- library/docs/development-de-temporary-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
