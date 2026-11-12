# Engineering contract: MM-STREAM-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement marshmallow.streaming.iterload(schema,records,*,errors="raise",partial=None,unknown=None) and Schema.iterload with frozen LoadResult(index,status,data,errors,valid_data). Validate options before consuming data, remain lazy, and call actual schema.load(many=False) per record so hooks/custom loads, partial and unknown policies work even for Schema(many=True). Raise retains original ValidationError; collect continues after invalid rows and reuses completed error_paths.flatten_errors, detaches valid_data and never stores raw input or exception objects. Non-validation exceptions must propagate; no global schema options or hook bypasses.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_mm_stream_dev.py and concise English compatibility documentation at library/docs/development-mm-stream-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/marshmallow/streaming.py
- library/src/marshmallow/schema.py
- library/development_tests/test_development_mm_stream_dev.py
- library/docs/development-mm-stream-dev.md
