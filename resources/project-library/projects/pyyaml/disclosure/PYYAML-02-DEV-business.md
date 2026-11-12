# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Normalize expected data-conversion errors of builtin bool/int/float/timestamp constructors into ConstructorError/YAMLError with node.start_mark and original cause where an underlying conversion failed. Handle empty/sign-only/nonnumeric/bad timestamp syntax and impossible calendar values. Check missing timestamp regex match explicitly rather than leaking AttributeError. Preserve legal types and ordinary constructors; do not broadly catch arbitrary Exception, TypeError/AttributeError from unknown programming mistakes or user custom constructor errors.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyyaml_02_dev.py, and English compatibility documentation at library/docs/development-pyyaml-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/lib/yaml/constructor.py
- library/tests/test_development_pyyaml_02_dev.py
- library/docs/development-pyyaml-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
