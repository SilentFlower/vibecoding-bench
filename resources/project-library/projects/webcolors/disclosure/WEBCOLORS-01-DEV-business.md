# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair the pinned CSS4 registry: export CSS4 at top level, use the actual CSS4 forward mapping and make names() default match existing conversion defaults (CSS4). rebeccapurple must work through names/name_to_hex/name_to_rgb/hex_to_name and the current HTML legacy named-color branch. Explicit older specifications remain unchanged and reject that name; canonical reverse aliases remain stable, returned names lists do not expose mutable internal state. Update inaccurate conversion default documentation, preserve the strict HTML simple-color API and the remaining legacy algorithm.

Deliver real implementation, original-failing public tests at library/tests/test_development_webcolors_01_dev.py, and English compatibility documentation at library/docs/development-webcolors-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/webcolors/_definitions.py
- library/src/webcolors/__init__.py
- library/src/webcolors/_html5.py
- library/src/webcolors/_conversion.py
- library/tests/test_development_webcolors_01_dev.py
- library/docs/development-webcolors-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
