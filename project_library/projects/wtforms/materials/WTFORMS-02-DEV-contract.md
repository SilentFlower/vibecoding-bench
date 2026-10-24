# Engineering contract: WTFORMS-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add wtforms.data_optional.DataOptional as opt-in Optional subclass. When raw_data is present, keep original Optional request/explicit-empty semantics, including clearing earlier processing errors for a deliberately empty request. Without submitted raw_data, use processed field.data: None/empty selected containers/empty string or configured whitespace is optional; 0 and False are real values and continue validators. Never erase an object conversion error merely because resulting data is None. Preserve old Optional untouched and use original StopValidation/field_flags/validator order. Document empty-container and whitespace policies explicitly.

Deliver real implementation, original-failing public tests at library/tests/test_development_wtforms_02_dev.py, and English compatibility documentation at library/docs/development-wtforms-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wtforms/data_optional.py
- library/tests/test_development_wtforms_02_dev.py
- library/docs/development-wtforms-02-dev.md
