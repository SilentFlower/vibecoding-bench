# Engineering contract: PYTHON-MARKDOWN-02-DEV

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Extend toc with opt-in unlisted_attribute="" (disabled default) and remove_unlisted_attribute=True. When enabled, presence of that exact heading attribute excludes only that heading from toc/toc_tokens, regardless of attribute value, preserving its real heading/id/body, anchor/permalink generation and descendant sections. Excluded parents do not prune child directory entries; surviving headings are nested by their real levels. Attribute removal is explicit and does not confuse data-toc-label or depth selection. Preserve default output and existing attr_list ordering, multiple markers, Unicode labels and reset behavior.

Deliver real implementation, original-failing public tests at library/tests/test_development_python_markdown_02_dev.py, and English compatibility documentation at library/docs/development-python-markdown-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/markdown/extensions/toc.py
- library/tests/test_development_python_markdown_02_dev.py
- library/docs/development-python-markdown-02-dev.md
