# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add BoxList.iter_jsonl_records(records, **json_kwargs), iter_jsonl(**json_kwargs) and write_jsonl(destination, *, encoding="utf-8", **json_kwargs). Encode one record at a time with standard JSON semantics and one trailing newline, preserve Unicode/options and nested Box values, and never materialize the complete input before yielding. Reject multiline indentation, report a safe one-based record number for encoding failures, support empty input and early generator close. Write to paths or caller-owned text streams without closing caller streams; preserve existing JSON/JSONL import behavior and state that write failures may leave a written prefix.

Deliver meaningful original-failing public regression tests at library/test/test_development_bx_jsonl_dev.py and concise English compatibility documentation at library/docs/development-bx-jsonl-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/box/box_list.py
- library/test/test_development_bx_jsonl_dev.py
- library/docs/development-bx-jsonl-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
