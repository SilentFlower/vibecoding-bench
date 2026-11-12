# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Forward existing ignore_extras/extras_key through recursive rows_from_file calls for explicit TSV and automatic CSV/TSV detection. All entry paths must collect extras list, ignore extras or default RowError identically, while short rows retain None and mutually exclusive options remain rejected before consumption. Preserve existing resource-close iterator behavior, explicit dialect and data values. Do not bypass bad rows, change CLI default truncate policy or claim the automatic sniffing defect itself fixed by this goal.

Deliver real implementation, original-failing public tests at library/tests/test_development_sqlite_utils_04_dev.py, and English compatibility documentation at library/docs/development-sqlite-utils-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/sqlite_utils/utils.py
- library/tests/test_development_sqlite_utils_04_dev.py
- library/docs/development-sqlite-utils-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
