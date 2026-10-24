# Business scope and confirmation

Inspect the pinned real implementation and reproduction. Explain the call path, clarify requirements, propose a compatibility plan and wait for confirmation before editing. Then implement in the same workspace, run meaningful tests and repair independently reported failures. The entire investigation, confirmation, implementation and acceptance is ONE engineering objective.

Repair LCSSeq and LCSStr preparation/reconstruction for qval=None words, qval>1 qgrams and qval=1 ordinary str/list/tuple inputs. Prepare exactly once; recursive multi-input LCSSeq must not retokenize prepared units. Strings at qval=1 retain str results; words/qgrams return lists of original units; ordinary list/tuple preserve first-input representation and unhashable tokens work. Empty/single/multi-input and the 200-element branch boundary follow the same contract. similarity and normalized maximum count prepared units, never concatenated character lengths. Preserve the previously delivered custom-predicate LCSSeq behavior and old character results/tie rules. This is one complete sequence-unit repair across both algorithms, not separate micro-goals for each branch.

Deliver real implementation, original-failing public tests at library/tests/test_development_textdistance_02_dev.py, and English compatibility documentation at library/docs/development-textdistance-02-dev.md. Preserve frozen original tests, environment and test controls. Only modify authorized paths.

Authorized paths:
- library/textdistance/algorithms/sequence_based.py
- library/tests/test_development_textdistance_02_dev.py
- library/docs/development-textdistance-02-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
