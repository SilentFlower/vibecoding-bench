# Engineering contract: WTFORMS-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add wtforms.derive.derive_form(base,name,fields,remove=(),replace=False) returning a new Form class through its actual metaclass. Preserve inherited Meta/inline validators and deterministic base-field order, append new mapping-order fields, keep overridden fields in their original slot and support explicit inherited-field removal. Reject reserved/private/invalid names, non-UnboundField values, unknown removals, simultaneous remove/readd and accidental override without replace=True. Do not mutate parent class, caches, field creation counters or existing instances; independent derived forms bind independent Field objects. This is a supported dynamic-class construction feature, not a claim existing WTForms cannot use type()/BaseForm at all.

Deliver real implementation, original-failing public tests at library/tests/test_development_wtforms_05_dev.py, and English compatibility documentation at library/docs/development-wtforms-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wtforms/derive.py
- library/tests/test_development_wtforms_05_dev.py
- library/docs/development-wtforms-05-dev.md
