# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add keyword-only random_source=None to wait_random, wait_random_exponential and wait_exponential_jitter. None retains the existing random module and mockability; an explicit source supplies random() or uniform() as required. Validate the needed method, preserve bounds, exponential overflow handling, existing positional parameters and every old wait result formula. Independent random.Random sources must be reproducible without reseeding or consuming global random state. Composition must still work; do not add dependencies.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tn_random_source_dev.py and concise English compatibility documentation at library/docs/development-tn-random-source-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/tenacity/wait.py
- library/development_tests/test_development_tn_random_source_dev.py
- library/docs/development-tn-random-source-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
