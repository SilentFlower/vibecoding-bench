# Engineering contract: AP-PROTOCOL-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix unstarted __AliveBarIteratorAdapter.__getattr__: unknown/private/protocol names raise AttributeError so hasattr/getattr(default)/iterable inspection work; known public handle controls retain the original UserWarning before iteration. Do not start/consume the source or create a progress bar while probing. After start, delegation and read-only/setter semantics remain unchanged. Resolve known names from the actual handle class dictionary, not a duplicated hand-maintained field list.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ap_protocol_dev.py and concise English compatibility documentation at library/docs/development-ap-protocol-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/alive_progress/core/progress.py
- library/development_tests/test_development_ap_protocol_dev.py
- library/docs/development-ap-protocol-dev.md
