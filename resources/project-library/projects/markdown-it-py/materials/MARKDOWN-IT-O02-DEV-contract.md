# Engineering contract: MARKDOWN-IT-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Fix actual MarkdownIt.enable/disable to fully materialize a nonstring Iterable once before dispatching names across all parser rule chains and missed-name detection. List/tuple/generator/one-shot iterators must produce identical active sets and rendering; unknown generator names still raise unless ignoreInvalid. If iteration itself raises after yielding a name, no rule chain may already be mutated. Preserve string, duplicate-name, empty input and existing rule-manager semantics; do not add pretend rules or special-case table alone.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdown_it_o02_dev.py and concise English compatibility documentation at library/docs/development-markdown-it-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdown_it/main.py
- library/tests/test_development_markdown_it_o02_dev.py
- library/docs/development-markdown-it-o02-dev.md
