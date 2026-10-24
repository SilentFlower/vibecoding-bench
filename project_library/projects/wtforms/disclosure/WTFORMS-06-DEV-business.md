# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add wtforms.batch.validate_records(form_class,records,multi_values=(),max_records=None,stop_on_error=False) yielding independent RecordResult(index,record_id,valid,data,errors). Consume (id,JSON payload) records lazily, use the earlier explicit JSONFormData adapter with actual Form.validate and nested fields, preserve duplicate/arbitrary original IDs and input order, and snapshot processed data/errors. First next must not preconsume later records; zero budget does not consume; optional first-error stops after yielding that failure. Exceeding a finite budget raises with explicit partial-results meaning (one extra record may be read to detect excess), never claim whole-stream success. Programming/source/validator exceptions propagate, and no files/network/HTTP services are accessed.

Deliver real implementation, original-failing public tests at library/tests/test_development_wtforms_06_dev.py, and English compatibility documentation at library/docs/development-wtforms-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/wtforms/batch.py
- library/tests/test_development_wtforms_06_dev.py
- library/docs/development-wtforms-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
