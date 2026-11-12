# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add funcy.pipeline Stage, Pipeline and PipelineResult using real Funcy make_func selectors. Validate unique nonempty names, callable optional input/output adapters and explicit raise/report policy. Run stages once in order with unary function protocol; an empty pipeline is identity, optional run(report=True) returns final value plus stage-only events without retaining inputs/intermediate business values. Default PipelineStageError carries name/index/input-function-output phase and original __cause__; report policy returns fixed failure result and stops later stages, omitting value-bearing exception text. Reject async stages/awaitable results explicitly, preserve original compose/rcompose and no implicit retry.

Deliver meaningful original-failing public regression tests at library/tests/test_development_funcy_o06_dev.py and concise English compatibility documentation at library/docs/development-funcy-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/funcy/pipeline.py
- library/tests/test_development_funcy_o06_dev.py
- library/docs/development-funcy-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
