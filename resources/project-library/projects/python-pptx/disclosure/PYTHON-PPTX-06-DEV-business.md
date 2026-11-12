# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pptx.layout.align_shapes/distribute_shapes for unique same-parent nonrotated axis-aligned shapes. Align left/right/top/bottom/centers to collective bounding box, centers floor to EMU integer. Distribution stable by position, preserve outermost edges, subtract actual unequal sizes and use rational gaps with nearest-even integer rounding, reject negative available gap. Validate full batch before mutation and rollback coordinate setter failure; preserve dimensions, shape IDs/Z order/content/relationships and input order return. Reject cross-space/rotated cases rather than claiming visual bounding boxes; saved geometry/reopen proof.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_pptx_06_dev.py, and English compatibility documentation at library/docs/development-python-pptx-06-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pptx/layout.py
- library/tests/test_development_python_pptx_06_dev.py
- library/docs/development-python-pptx-06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
