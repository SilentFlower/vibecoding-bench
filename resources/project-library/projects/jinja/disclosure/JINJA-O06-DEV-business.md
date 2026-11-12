# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add jinja2.loaders.ResourcesLoader(BaseLoader) accepting an explicit Traversable root, encoding, reload="content"|"immutable" and nonnegative inventory budgets. Read real resource text through the protocol and reuse BaseLoader compilation/inheritance/cache; support filesystem Path and zipfile.Path without fspath coercion. Validate template components against traversal/absolute/backslash/NUL names, additionally resolve/confine filesystem Path symlinks, and return sorted inventory without silently truncating beyond depth/count budgets. content rechecks source instead of pretending generic resources have mtime; immutable explicitly caches. Preserve existing FileSystem/Package loaders, propagate encoding/resource errors and state that a supplied abstract resource implementation is trusted rather than a universal OS sandbox.

Deliver meaningful original-failing public regression tests at library/tests/test_development_jinja_o06_dev.py and concise English compatibility documentation at library/docs/development-jinja-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/src/jinja2/loaders.py
- library/tests/test_development_jinja_o06_dev.py
- library/docs/development-jinja-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
