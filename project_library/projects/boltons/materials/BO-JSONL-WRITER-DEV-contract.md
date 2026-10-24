# Engineering contract: BO-JSONL-WRITER-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add jsonutils.JSONLWriter(stream,*,binary=False,encoding="utf-8",dumps=None), write(value), write_many(iterable), flush() and successful count. Serialize and validate one complete JSON text before writing exactly one LF-terminated record; reject physical CR/LF, nonstring or invalid custom serializer results without writing that record. Binary mode encodes first; preserve caller stream ownership and lazy consumption, detect reported short writes, propagate serialization/I/O errors and keep prior successful records/count. No whole-batch rollback or silent stream closure.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_bo_jsonl_writer_dev.py and concise English compatibility documentation at library/docs/development-bo-jsonl-writer-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/boltons/jsonutils.py
- library/development_tests/test_development_bo_jsonl_writer_dev.py
- library/docs/development-bo-jsonl-writer-dev.md
