# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add Slide.transition proxy with nonmutating configuration read, configure fade/push/wipe with XSD l/r/u/d directions, slow/med/fast speed, bool advance_on_click and optional unsignedInt advance_after_ms; clear explicitly removes transition. Validate entire update before mutation, insert p:transition before timing/extLst per pinned pml.xsd, preserve existing attrs/sound/extensions, refuse unknown existing effect replacement until explicit clear. Real PPTX XML/reopen proof; no autoplay execution, precise visual-effect duration or rendering claim.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_pptx_02_dev.py, and English compatibility documentation at library/docs/development-python-pptx-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/src/pptx/slide.py
- library/src/pptx/transition.py
- library/tests/test_development_python_pptx_02_dev.py
- library/docs/development-python-pptx-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
