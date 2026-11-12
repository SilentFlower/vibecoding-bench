# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement tablib.loading.load_records(records,columns,*,aliases=None,missing="raise",extra="raise",converters=None,errors="raise",title=None) returning completed ConversionResult. Output column order is explicit; aliases map output names to unique external keys. Validate missing raise/none and extra raise/ignore, consume mapping records once and detach values. Use actual Dataset.dict loading with canonical header prototype while retaining each later mapping order, requiring completed alignment repair; remove prototype before output. Compose actual convert_columns, preserve false/zero/empty/None, support empty input, fail without partial output and never mutate incoming records.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_tb_load_dev.py and concise English compatibility documentation at library/docs/development-tb-load-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/tablib/loading.py
- library/development_tests/test_development_tb_load_dev.py
- library/docs/development-tb-load-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
