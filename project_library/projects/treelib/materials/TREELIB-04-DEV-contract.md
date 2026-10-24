# Engineering contract: TREELIB-04-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add treelib.csvio.read_csv(stream,tree_class=Tree,**tree_kwargs)/write_csv(tree,stream) for an explicit id,parent,tag,data header (exact unique columns/order). IDs and parents are separate from display tags, empty parent denotes root, data is strict JSON text, standard CSV quoting preserves commas/newlines/Unicode. Read valid out-of-order rows through the delivered complete Tree.from_map validation; reject duplicate/empty IDs, wrong field counts/headers, invalid JSON, missing parents and detached cycles instead of losing rows. Write full descendants in current sibling order regardless of expanded, without closing or rewinding caller streams. Tags may be empty without becoming root markers. Preserve original file APIs and document that expanded is a snapshot capability, not a CSV field.

Deliver real implementation, original-failing public tests at library/tests/test_development_treelib_04_dev.py, and English compatibility documentation at library/docs/development-treelib-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/treelib/csvio.py
- library/tests/test_development_treelib_04_dev.py
- library/docs/development-treelib-04-dev.md
