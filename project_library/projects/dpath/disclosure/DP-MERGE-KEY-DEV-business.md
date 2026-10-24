# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement dpath.keymerge.merge_by_key(left,right,key). Materialize and validate both record iterables before merging: every mapping has a hashable business key and no duplicates within a side, using (type,value) identity so bool/int/string keys are not silently conflated. Preserve left order, recursively merge matching dictionary fields with right scalar/list replacement, append new records in right order, and deep-copy all retained/incoming nodes. Reject malformed/duplicate/unhashable keys without mutating either input. Do not change default dpath.merge list concatenation or original source references.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_dp_merge_key_dev.py and concise English compatibility documentation at library/docs/development-dp-merge-key-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/dpath/keymerge.py
- library/development_tests/test_development_dp_merge_key_dev.py
- library/docs/development-dp-merge-key-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
