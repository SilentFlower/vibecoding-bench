# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add IncrementalParser(encoding=None,*,process_namespaces=False,namespace_separator=":",disable_entities=True,process_comments=False,**handler_options) with feed(chunk) and close(). Reuse pinned SAX handler, including completed resource budgets, item callbacks and postprocessor. Support UTF8 byte boundaries and text chunks, require consistent bytes/str chunk types, finalize incomplete XML with original ExpatError, make successful close idempotent and prohibit feed after close or any parse failure. Entity declarations remain disabled by default and callback interruption propagates immediately. No threads, buffering an entire input document, or restarting after failure.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_xd_incremental_dev.py and concise English compatibility documentation at library/docs/development-xd-incremental-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/xmltodict.py
- library/development_tests/test_development_xd_incremental_dev.py
- library/docs/development-xd-incremental-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
