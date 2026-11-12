# Engineering contract: WTFORMS-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add wtforms.partial.validate_fields(form,paths,extra_validators=None) and PartialResult(valid,validated,errors). paths are explicit segment tuples, supporting FormField names and strict integer FieldList indices; preflight unknown/duplicate/overlapping ancestor-descendant masks before any validation. Validate only selected targets through actual field.validate with owning form, explicit extras then original class inline validator, copying sequences without mutating caller lists. Return deep-copied path-associated errors, preserve every unselected error/state and support empty mask without claiming whole-form validity. Do not run/deem passed cross-field Form.validate overrides; document callers must perform full validation for global rules and that selected container fields invoke their normal whole-container rules.

Deliver real implementation, original-failing public tests at library/tests/test_development_wtforms_04_dev.py, and English compatibility documentation at library/docs/development-wtforms-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wtforms/partial.py
- library/tests/test_development_wtforms_04_dev.py
- library/docs/development-wtforms-04-dev.md
