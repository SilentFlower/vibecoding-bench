# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add webcolors.palette.Palette as an immutable Mapping of case-insensitive names to normalized RGB hex, with rgb(name), aliases(hex), to_dict(), stable sorted iteration, copied input/output ownership, and optional base_spec composition. conflict is error/brand/builtin; default collisions reject rather than silently alter standard colors. Reject empty/whitespace-padded names, case-only duplicates, invalid hex and unknown policy/spec. Independent palettes with the same primary name never interfere, and custom names are not registered in global CSS tables. Aliases return a stable immutable tuple and every query uses the actual candidate conversion functions. Preserve all old name/spec/reverse-alias contracts.

Deliver real implementation, original-failing public tests at library/tests/test_development_webcolors_06_dev.py, and English compatibility documentation at library/docs/development-webcolors-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/webcolors/palette.py
- library/tests/test_development_webcolors_06_dev.py
- library/docs/development-webcolors-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
