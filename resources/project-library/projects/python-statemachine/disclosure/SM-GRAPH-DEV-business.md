# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement statemachine.transition_graph.TransitionGraph(machine_class), frozen Edge(source,target,event), nodes/edges tuples and shortest_path(start,target,*,max_depth=1000). Inspect actual StateMachine states/transitions/events, stable-deduplicate edges, support cycles/self/targetless transitions and shortest event sequences with bounded BFS. Same state yields empty path, unavailable path None, unknown IDs error. Explicitly reject hierarchical/parallel/eventless/multitarget definitions rather than pretending flat graph equals runtime. Do not instantiate machines, evaluate guards/callbacks or promise candidate paths will be enabled; preserve declaration objects.

Deliver meaningful original-failing public regression tests at library/development_tests/test_development_sm_graph_dev.py and concise English compatibility documentation at library/docs/development-sm-graph-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/statemachine/transition_graph.py
- library/development_tests/test_development_sm_graph_dev.py
- library/docs/development-sm-graph-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
