# Engineering contract: AT-VALIDATION-REPORT-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add validate_all(instance, *, raise_errors=False), ValidationIssue and MultiValidationError under attr.validation and attrs.validation. Report the first original Exception from each independent validated field in declaration order, retaining the real Attribute object, real field name and exception object. Invoke each field validator once and preserve its existing and_/or_/optional/deep fail-fast and one-pass semantics; do not reinterpret nested paths or replay validators. Continue other independent fields, catch Exception only, honor the shared validation disable switch, and optionally raise a MultiValidationError with an issues tuple. Do not mutate fields or replace ordinary attrs.validate fail-fast behavior.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_at_validation_report_dev.py and concise English compatibility documentation at library/docs/development-at-validation-report-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/attr/validation.py
- library/src/attrs/validation.py
- library/development_tests/test_development_at_validation_report_dev.py
- library/docs/development-at-validation-report-dev.md
