# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pyparsing.recovery.parse_recovering(expression,text,separator=";",quote="\"",escape="\\") with immutable RecoveryResult, AcceptedRecord and RejectedRecord. Split only at explicit single-character separators outside quoted/escaped text, including multiline records. Parse each nonblank record completely using real grammar; retain successful ParseResults plus original absolute start/end and ordered failures with original ParseException and absolute offset. Skip blank records only; unclosed quoted tail remains one failed record rather than inventing internal boundaries. Propagate ParseFatalException and ordinary action exceptions, explicitly do not roll back action side effects. Preserve strict default parse_string and original keepTabs.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyparsing_06_dev.py, and English compatibility documentation at library/docs/development-pyparsing-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyparsing/recovery.py
- library/tests/test_development_pyparsing_06_dev.py
- library/docs/development-pyparsing-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
