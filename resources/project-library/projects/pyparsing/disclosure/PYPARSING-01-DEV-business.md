# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Add pyparsing.grammar_tools.lint_grammar returning immutable GrammarIssue(code,path,node_type,message) entries. Traverse real ParserElement.recurse graph once by identity, safely handling shared nodes and Forward cycles. Report undefined Forward, repetition of explicit Empty, and literal alternatives shadowed by earlier literal prefixes in MatchFirst without parse actions. Do not parse, execute user actions/conditions, mutate grammar, stringify cyclic nodes or claim exhaustive lint of custom/dynamic expressions. Preserve existing validate/parse behavior.

Deliver real implementation, original-failing public tests at library/tests/test_development_pyparsing_01_dev.py, and English compatibility documentation at library/docs/development-pyparsing-01-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/pyparsing/grammar_tools.py
- library/tests/test_development_pyparsing_01_dev.py
- library/docs/development-pyparsing-01-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
