# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add the actual Validator finite boolean rule with schema-validated arguments and native error-tree integration. When enabled reject NaN/positive or negative Infinity and nonnumeric/bool values, support finite int/float and registered Decimal types without converting large Decimals through float, and work in nested records. finite=False and absent finite preserve existing number/min/max policies; do not alter global types or claim existing bool exclusion as a separate feature.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cerberus_o02_dev.py and concise English compatibility documentation at library/docs/development-cerberus-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cerberus/validator.py
- library/tests/test_development_cerberus_o02_dev.py
- library/docs/development-cerberus-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
