# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement inflect.streams.iter_join(words,*,sep=", ",pair=" and ",final=", and ") yielding text chunks. Handle zero/one/two/many elements distinctly, consume only finite lookahead (at most three items before first output) and never materialize the whole iterable. Explicit separators avoid the existing join automatic comma scan and can disable Oxford comma. Reject bare str/bytes and non-string words, propagate generator errors, preserve empty string elements and backpressure. Existing engine.join remains unchanged; partial emitted streams are not promised transactional.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_if_stream_join_dev.py and concise English compatibility documentation at library/docs/development-if-stream-join-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/inflect/streams.py
- library/development_tests/test_development_if_stream_join_dev.py
- library/docs/development-if-stream-join-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
