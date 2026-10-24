# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement ftfy.streaming.fix_chunks(chunks,config=None,*,max_line_length=1000000). Assemble physical LF lines across arbitrary Unicode chunk boundaries (including CRLF and mojibake sequences), then use actual fix_file semantics including sticky auto-HTML policy across lines. Preserve final unterminated line, ignore empty chunks, stay lazy and buffer at most one bounded physical line. Validate positive character budget/config before consuming input, reject non-text chunks and over-budget lines before repairing them. Results must equal fix_file(StringIO(joined_input)) without materializing the full input or changing old fix_file.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_ft_chunks_dev.py and concise English compatibility documentation at library/docs/development-ft-chunks-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/ftfy/streaming.py
- library/development_tests/test_development_ft_chunks_dev.py
- library/docs/development-ft-chunks-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
