# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add optional reference_datetime=None to Date and DateTime constructors. When supplied, it must be a naive datetime; reject dates, strings and aware datetimes with TypeError before parsing. Use this fixed wall-clock anchor for natural-language relative date parsing. Preserve explicit format and ISO handling, timezone parameter behavior, null handling and old defaults (Date uses ZERO_DT, DateTime captures today at midnight). Keep the anchor across pickle round trips and preserve old Date pickle states.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ag_reference_dev.py and concise English compatibility documentation at library/docs/development-ag-reference-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/agate/data_types/date.py
- library/agate/data_types/date_time.py
- library/development_tests/test_development_ag_reference_dev.py
- library/docs/development-ag-reference-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
