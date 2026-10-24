# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair parsedate and parsedatetime to apply existing IGNORE/SET_NULL policy to genuine dateutil OverflowError as well as ParserError. Keep original value for IGNORE, None for SET_NULL, and re-raise original exception under default/unknown policy; preserve legal date/dayfirst/yearfirst, empty/falsy and normal parser error behavior. Do not catch arbitrary TypeError/RuntimeError or convert out-of-range dates into guessed valid values. Prove real huge-year data and both recipe entry points.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlite_utils_05_dev.py, and English compatibility documentation at library/docs/development-sqlite-utils-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlite_utils/recipes.py
- library/tests/test_development_sqlite_utils_05_dev.py
- library/docs/development-sqlite-utils-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
