# Engineering contract: DOCUTILS-O05-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add actual json Writer and doctree_json to_data/from_data/dumps/loads schema 1 for the declared supported standard node whitelist, preserving node type/rawsource/source/line/JSON attributes/child order/Unicode and rebuilding actual id/name maps. Real published JSON must round-trip into real Docutils nodes and publish through HTML with reference ids intact. Never pickle, deserialize arbitrary classes or serialize settings/reporter objects. Reject unknown schemas/nodes/extra shapes, invalid source/line/attributes, opaque/nonfinite values, duplicate ids, shared/cyclic nodes and explicit depth/node-budget overflow. Unsupported standard/custom nodes must fail explicitly rather than silently losing information; old XML/pseudoxml remain unchanged.

Deliver meaningful original-failing public regression tests at library/tests/test_development_docutils_o05_dev.py and concise English compatibility documentation at library/docs/development-docutils-o05-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/docutils/docutils/doctree_json.py
- library/docutils/docutils/writers/json.py
- library/tests/test_development_docutils_o05_dev.py
- library/docs/development-docutils-o05-dev.md
