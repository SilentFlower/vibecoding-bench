# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add liquid.context_schema.ContextField(path tuple[str|int],expected_type,required=True,nullable=False), ContextSchema and validate_context(data,schema). Read declared Mapping/list/tuple paths only; report all missing and wrong-type fields in declaration order without values. Support explicit list indices, optional missing and nullable None separately; bool cannot satisfy int. Do not render templates, invoke filters or arbitrary object getters, infer filter types or declare dynamic paths complete. Schema copies field declarations, rejects duplicate/invalid paths, and extra undeclared data remains allowed. Default rendering behavior stays unchanged.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_liquid_03_dev.py, and English compatibility documentation at library/docs/development-python-liquid-03-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/liquid/context_schema.py
- library/tests/test_development_python_liquid_03_dev.py
- library/docs/development-python-liquid-03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
