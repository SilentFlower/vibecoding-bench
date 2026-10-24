# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add wtforms.jsondata.JSONFormData implementing getlist, iteration, contains, length and first-value lookup. Snapshot a top-level JSON mapping into standard hyphen form paths: objects recurse, lists use numeric FieldList indices unless the complete path is explicitly listed in multi_values for SelectMultiple. Define None as present empty string, booleans true/false, finite numbers decimal text, strings unchanged; missing keys stay absent and explicit empty multi-value list stays present. Reject hyphen-containing/empty/nonstring keys, path collisions, unsupported objects/nonfinite numbers, excessive depth/value budget and malformed roots. Preserve caller ownership and never auto-treat arbitrary dict formdata or change data/obj semantics. Validate with actual FormField/FieldList/SelectMultiple processing and nested error locations.

Deliver real implementation, original-failing public tests at library/tests/test_development_wtforms_03_dev.py, and English compatibility documentation at library/docs/development-wtforms-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wtforms/jsondata.py
- library/tests/test_development_wtforms_03_dev.py
- library/docs/development-wtforms-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
