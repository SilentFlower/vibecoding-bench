# Engineering contract: MARKDOWN-IT-O06-DEV

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Add SyntaxTreeNode.insert_child(index,node), append_child(node), remove_child(node) and replace_child(old,new). Maintain exactly one parent and consistent sibling traversal, moving an existing node out of its old parent; insertion indices are pre-move positions 0..len(children), adjusted when moving a preceding same-parent node. Reject root/self/ancestor insertion, leaf containers, wrong old parents and invalid indices before detaching anything. Synchronize actual token.children for inline/image containers so to_tokens followed by real rendering reflects edits. Keep existing read APIs and do not claim direct external list mutations are protected. Return inserted/removed nodes as documented, including idempotent self-replacement.

Deliver meaningful original-failing public regression tests at library/tests/test_development_markdown_it_o06_dev.py and concise English compatibility documentation at library/docs/development-markdown-it-o06-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/markdown_it/tree.py
- library/tests/test_development_markdown_it_o06_dev.py
- library/docs/development-markdown-it-o06-dev.md
