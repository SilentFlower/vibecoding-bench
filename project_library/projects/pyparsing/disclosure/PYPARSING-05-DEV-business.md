# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pyparsing.diagnostics.to_diagnostic(error) for real ParseBaseException only. Return fresh schema1 data with code parse-error/parse-fatal, clamped character offset/end_offset, one-based character line/column, EOF, exact original msg and optional parser node type. EOF span is zero-width; Unicode is character-counted, not bytes/display width. Keep expected=None rather than invent complete alternatives. Do not mutate exception, grammar or existing str/explain, and reject ordinary user action errors instead of misclassifying them as parser failures.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyparsing_05_dev.py, and English compatibility documentation at library/docs/development-pyparsing-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyparsing/diagnostics.py
- library/tests/test_development_pyparsing_05_dev.py
- library/docs/development-pyparsing-05-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
