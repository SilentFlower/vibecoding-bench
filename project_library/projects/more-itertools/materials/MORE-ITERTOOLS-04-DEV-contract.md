# Engineering contract: MORE-ITERTOOLS-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add asof_join(left,right,key,*,right_key=None,tolerance=None,default=None) yielding (left event,last right event whose time <= left time). Equal right timestamps select last input version; optional nonnegative tolerance inclusive, explicit unmatched default. Preserve original identities, one-shot ordering, separate right key, empty streams and finite lookahead memory. Reject reverse timestamps as observed; do not eagerly validate unconsumed tail, sort entire streams or use nearest future values. No dependency on equality join.

Deliver real implementation, original-failing public tests at library/tests/test_development_more_itertools_04_dev.py, and English compatibility documentation at library/docs/development-more-itertools-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/more_itertools/more.py
- library/more_itertools/_asof_join.py
- library/tests/test_development_more_itertools_04_dev.py
- library/docs/development-more-itertools-04-dev.md
