# Engineering contract: PETL-06-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair toxml built-in tag/name/attribute styles to escape text versus attribute quotes exactly once; independent ElementTree parsing must recover original &, angle brackets, both quotes and Unicode. Escape displayed header text while retain original format field lookup; validate XML names for built-in structural paths/name-keys/attribute-keys and reject prohibited control characters. Keep custom raw format templates/prologue/epilogue explicitly raw and existing valid layout/None string behavior. Validation during streaming may leave partial target on bad later data; no atomic-write promise. Do not alter original tests.

Deliver real implementation, original-failing public tests at library/tests/test_development_petl_06_dev.py, and English compatibility documentation at library/docs/development-petl-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/petl/io/xml.py
- library/tests/test_development_petl_06_dev.py
- library/docs/development-petl-06-dev.md
