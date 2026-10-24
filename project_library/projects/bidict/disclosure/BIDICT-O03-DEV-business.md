# Business scope and confirmation

Inspect the pinned real source and public reproduction, explain the actual call path, ask necessary clarification questions, propose a concrete compatibility plan and wait for my confirmation before editing. Then implement and validate in this same conversation and workspace. Fix any independently reported failures before delivery. The complete engineering contract is:

Implement bidict.transform.transform_items(mapping, *, key_fn=None, value_fn=None). Transform each original key/value exactly once into a new same-type ordered relation, validate both transformed key and value uniqueness before constructing/publishing, and report one-based conflicting source positions rather than silently dropping rows. Preserve inputs, inverse behavior, frozen/custom subclasses, callback exception identity and natural unhashable errors.

Deliver meaningful original-failing public regression tests at library/tests/test_development_bidict_o03_dev.py and concise English compatibility documentation at library/docs/development-bidict-o03-dev.md. Preserve all frozen original tests, dependency metadata and test controls. Change only authorized paths.

Authorized paths:
- library/bidict/transform.py
- library/tests/test_development_bidict_o03_dev.py
- library/docs/development-bidict-o03-dev.md

Public examples do not cover every acceptance boundary. Preserve the original tests, environment and independent verifier.
