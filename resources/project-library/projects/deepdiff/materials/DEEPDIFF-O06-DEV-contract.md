# Engineering contract: DEEPDIFF-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add deepdiff.reporting.redacted_report(diff,*,redact_paths=(),mask="[已遮蔽]",left_label="left",right_label="right",default_mapping=None) for explicit JSON-tree diff categories. Use actual verbose text representation from text/tree input, preserve category/path/type facts and independent display labels while masking matching values before serialization. Support exact/ancestor paths and native component * / ** wildcards without confusing a literal star key; also traverse coarse parent replacement payloads so child redactions cannot leak. Drop value-bearing multiline diff text when redaction is enabled. Reject unsupported pathless/set categories and invalid labels/paths, apply custom type serializers only after masking, return JSON-safe schema1 report and never mutate original Diff/Delta or source trees.

Deliver meaningful original-failing public regression tests at library/tests/test_development_deepdiff_o06_dev.py and concise English compatibility documentation at library/docs/development-deepdiff-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/deepdiff/reporting.py
- library/tests/test_development_deepdiff_o06_dev.py
- library/docs/development-deepdiff-o06-dev.md
