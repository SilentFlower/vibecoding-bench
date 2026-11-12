# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair both BaseForm.process extra_filters and Form.validate extra_validators as one caller-ownership bug family. Before appending an inline rule, copy only that used field sequence; do not mutate caller lists, deep-copy callable objects, reorder explicit-extra before inline, or eagerly consume unrelated unused extra-field generators. Support list/tuple sequences, repeat construction/process/validate, inheritance and real error propagation. Each inline runs once per current processing/validation cycle. Preserve all original field/validator semantics and leave already-correct default behavior unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_wtforms_01_dev.py, and English compatibility documentation at library/docs/development-wtforms-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wtforms/form.py
- library/tests/test_development_wtforms_01_dev.py
- library/docs/development-wtforms-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
