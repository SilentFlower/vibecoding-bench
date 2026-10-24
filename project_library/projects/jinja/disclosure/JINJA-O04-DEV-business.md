# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Extend actual TemplateStream.dump to recognize str/bytes/os.PathLike via os.fspath before opening owned binary files, keeping default UTF-8 and explicit encoding/errors. Never coerce arbitrary objects with str. Preserve buffered/unbuffered streamed output, existing file-like writelines/write behavior and caller-owned stream lifetime; owned files close on write/encode failure. Reject bad __fspath__ return types through standard semantics and prove Unicode byte parity with string paths.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jinja_o04_dev.py and concise English compatibility documentation at library/docs/development-jinja-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/jinja2/environment.py
- library/tests/test_development_jinja_o04_dev.py
- library/docs/development-jinja-o04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
