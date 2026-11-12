# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add explicit pyparsing.dataclass_results.to_dataclass(results,model,strict=True) and ResultMappingError(path). Consume real ParseResults named mappings or Mapping; support dataclass init fields, required/default/default_factory fields, nested dataclasses, list[T], optional/union and already correctly typed primitive values. No automatic scalar coercion or arbitrary type construction; bool must not populate int. Strict mode rejects extra keys, optional strict=False ignores only extras; missing/type errors report exact nested path. Cap recursion and preserve original ParseResults/mappings and existing as_dict/as_list semantics.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyparsing_04_dev.py, and English compatibility documentation at library/docs/development-pyparsing-04-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyparsing/dataclass_results.py
- library/tests/test_development_pyparsing_04_dev.py
- library/docs/development-pyparsing-04-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
