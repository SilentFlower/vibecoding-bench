# Engineering contract: BIDICT-O02-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bidict.select.select(mapping, *, keys=None, values=None, predicate=None, strict=False). Combine requested key/value/predicate filters, distinguish absent filters from empty selections, retain original relative order and concrete bidict/frozen/ordered/custom type and inverse behavior. One-shot filters are consumed once. Strict missing requests raise before callbacks, callbacks propagate normally and result backing must be independent of source mutation.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bidict_o02_dev.py and concise English compatibility documentation at library/docs/development-bidict-o02-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bidict/select.py
- library/tests/test_development_bidict_o02_dev.py
- library/docs/development-bidict-o02-dev.md
