# Engineering contract: SJ-POINTER-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement simplejson.pointer.tokens(pointer), index(token,length,*,append=False) and resolve(document,pointer). Support empty root, empty mapping keys and RFC6901 ~0/~1 escapes with exact one-pass semantics. Reject malformed escapes, URI fragments, non-string pointers and non-canonical array indices (negative, leading zero, bool-like, dash except append mode). Mappings keep numeric-looking string keys; arrays use bounds-checked numeric indices. Resolution returns the original referenced value and never mutates the input.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sj_pointer_dev.py and concise English compatibility documentation at library/docs/development-sj-pointer-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/simplejson/pointer.py
- library/development_tests/test_development_sj_pointer_dev.py
- library/docs/development-sj-pointer-dev.md
