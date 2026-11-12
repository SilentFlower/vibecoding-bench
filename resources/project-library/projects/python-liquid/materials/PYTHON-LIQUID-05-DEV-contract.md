# Engineering contract: PYTHON-LIQUID-05-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add liquid.template_bundle.make_bundle/templates explicit source Mapping plus root entries, load_bundle and immutable TemplateBundle with fresh environment(). Canonical schema1 JSON stores only raw source strings, explicit roots and SHA256 of canonical payload; reject tampering, duplicate JSON keys, unknown schema/fields, bad source types, missing/duplicate roots. Preserve all supplied dependency sources and prove real render/include in a fresh DictLoader environment. No pickle/code objects, no automatic dynamic-dependency completeness claim, no plugin/environment identity guessing; caller supplies compatible explicit options and cannot replace bundle loader. Copy sources and expose readonly snapshot.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_liquid_05_dev.py, and English compatibility documentation at library/docs/development-python-liquid-05-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/liquid/template_bundle.py
- library/tests/test_development_python_liquid_05_dev.py
- library/docs/development-python-liquid-05-dev.md
