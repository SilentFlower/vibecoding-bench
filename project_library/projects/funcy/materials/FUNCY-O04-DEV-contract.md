# Engineering contract: FUNCY-O04-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add funcy.walktree.tree_walk(root,*,children=None,follow=None,prune=None,max_depth=None), frozen WalkEvent(event,path,depth,node,pruned) and TreeCycleError(path). Default mapping keys/sequence indexes use real Funcy is_seqcont, keeping text/bytes leaves; explicit children yields labeled edges. Generate stable lazy pre/post events with an iterative stack, prune before children access and support nonnegative depth cap. Detect ancestor cycles by identity while allowing shared acyclic nodes under separate paths, propagate callbacks/source errors and leave inputs unchanged. Prove deep 1500-level trees, exact event order and balanced pruned nodes without changing old tree_nodes/leaves.

Deliver meaningful original-failing public regression tests at library/tests/test_development_funcy_o04_dev.py and concise English compatibility documentation at library/docs/development-funcy-o04-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/funcy/walktree.py
- library/tests/test_development_funcy_o04_dev.py
- library/docs/development-funcy-o04-dev.md
