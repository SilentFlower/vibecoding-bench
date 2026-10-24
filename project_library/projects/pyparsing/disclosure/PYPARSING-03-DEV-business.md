# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pyparsing.decimal_input.localized_decimal returning a real ParserElement that emits Decimal directly. Explicit decimal_separator, optional group_separator, positive group_size and optional nonnegative max_fraction define exact syntax; do not query host locale, use float or infer locales. Support ASCII digits, optional sign, ungrouped integers or strict first-short/subsequent-fixed groups, optional fractional part, Unicode grouping separator and precision. Invalid grouping/fraction/scientific syntax fails with normal parse_all semantics. Preserve existing pyparsing.common numbers.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyparsing_03_dev.py, and English compatibility documentation at library/docs/development-pyparsing-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyparsing/decimal_input.py
- library/tests/test_development_pyparsing_03_dev.py
- library/docs/development-pyparsing-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
