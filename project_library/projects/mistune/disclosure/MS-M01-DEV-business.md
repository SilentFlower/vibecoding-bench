# Business scope

Implement the complete public empty-document CLI contract, including actual -o file creation, explicit empty-message precedence and nonblocking interactive absence. Preserve nonempty/missing-file behavior and modify only the authorized implementation/test files with meaningful original-failing public tests.

# Investigation topics

- 定位空文档和未提供输入的混淆

# Supplied business material: materials/empty-cases.md

Compare the real candidate CLI with an empty stdin pipe; explicit -m ""; -f <zero-byte-file>; -m "" -o <new-output-file>; and -m "" -f <file-containing-a-heading>. Also compare -m 0, a missing file, and a real interactive TTY with no arguments. The API accepts an empty document. In the pinned CLI the first two cases report a missing message while the zero-byte file succeeds. All paths and data must be local and synthetic.


# Supplied business material: materials/empty-contract.md

Treat empty piped stdin and explicit -m "" as provided valid empty documents: exit 0 and use the ordinary renderer/output path. With -o, create an actual empty result file. Explicit -m, including an empty string, takes precedence over -f. Preserve existing nonempty messages/files, text 0 and missing-file failure. A real interactive TTY with no message/file still reports missing input and exits nonzero immediately, without blocking for input. Do not add AST JSON serialization, change default plugins/renderers, alter other output policy or test controls. Only library/src/mistune/__main__.py and library/tests/test_cli.py may change. Add meaningful original-failing public tests; preserve the complete frozen original main/subtest suite.

