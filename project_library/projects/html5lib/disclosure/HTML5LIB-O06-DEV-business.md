# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add links.collect_links(tree,*,treewalker="etree",document_url="") using actual HTML walker attributes. Apply the first nonempty base href relative to document_url, then list HTML href/src/poster/action resources in source order with element/attribute/raw/resolved/token_index/descriptor/status and stable resolved groups retaining duplicate occurrences. Preserve empty URI as empty, fragments and unknown schemes under standard urljoin; with no base keep relative values. Include ordinary srcset candidates with finite positive numeric x or positive integer w descriptors; retain malformed candidates with resolved=None/status=unparsed_srcset and explicitly mark ambiguous data: srcsets unparsed instead of claiming complete extraction. DOM/etree and unchanged tree semantics must agree; perform no fetch, path guessing or URI scheme authorization.

Deliver meaningful original-failing public regression tests at library/tests/test_development_html5lib_o06_dev.py and concise English compatibility documentation at library/docs/development-html5lib-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/html5lib/links.py
- library/tests/test_development_html5lib_o06_dev.py
- library/docs/development-html5lib-o06-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
