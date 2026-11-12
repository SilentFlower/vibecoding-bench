# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair Traceback.extract for the entire cause/context/ExceptionGroup graph using exception object identity IDs, not hashing or equality/text. Each exception appears at most once, self/multi-object cycles terminate, shared group members and unhashable custom exceptions work, normal chain order/is_cause/__suppress_context__ remain correct and notes belong to the actual current exception rather than being copied from the first. Propagate the same visited set through group recursion without prematurely marking unprocessed children. Preserve normal frame extraction/rendering and control test baseline cycles in a bounded subprocess so regression cannot hang indefinitely.

Deliver real implementation, original-failing public tests at library/tests/test_development_rich_02_dev.py, and English compatibility documentation at library/docs/development-rich-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/rich/traceback.py
- library/tests/test_development_rich_02_dev.py
- library/docs/development-rich-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
