# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add cssselect.batch.translate_many(records, *, translator=None, prefix="descendant-or-self::", fail_fast=False) as a lazy ordered iterator of records {id,css,ok,xpath,error}. Each input is (id, complete CSS group), including duplicate IDs; never concatenate groups or split commas. Catch only actual SelectorSyntaxError/ExpressionError into parse/translate diagnostics without value-bearing messages; continue other records, with explicit fail-fast rethrow. Forward actual translator and prefix, consume only requested inputs, propagate upstream generator and programmer errors and support empty batches.

Deliver meaningful original-failing public regression tests at library/tests/test_development_cssselect_o02_dev.py and concise English compatibility documentation at library/docs/development-cssselect-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/cssselect/batch.py
- library/tests/test_development_cssselect_o02_dev.py
- library/docs/development-cssselect-o02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
