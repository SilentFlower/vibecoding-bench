# Engineering contract: PYPARSING-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pyparsing.byte_input.parse_bytes(expression,data,*,encoding,parse_all=False), immutable ByteParseResult(results,text,byte_offsets), and ByteParseError(error,byte_offset). Require bytes and explicit supported codec UTF8/UTF8-SIG/ASCII/Latin1, reject other/stateful encodings rather than guess. Map every character boundary and EOF to original bytes including BOM. Use top-level grammar copy with tabs preserved; original grammar policy stays unchanged. Propagate strict UnicodeDecodeError, wrap only real ParseBaseException with exact original byte offset, retain original exception and results.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyparsing_02_dev.py, and English compatibility documentation at library/docs/development-pyparsing-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyparsing/byte_input.py
- library/tests/test_development_pyparsing_02_dev.py
- library/docs/development-pyparsing-02-dev.md
