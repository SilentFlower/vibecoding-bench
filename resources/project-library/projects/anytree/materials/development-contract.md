# Isolated JSON depth override

The application shares one DictExporter between full-tree exports and JSON previews. `JsonExporter(dictexporter=shared, maxlevel=1)` must limit this JSON result to the root, while `shared.maxlevel` and later shared exports remain unchanged.

* An explicit JSON maxlevel overrides the supplied exporter only for that call. Export and write have the same behavior, and two JSON exporters sharing one standard DictExporter can use independent depths in any order.
* When JSON maxlevel is None, use the supplied exporter's configured depth. Preserve dictcls, attriter and childiter, including their object identities and output order.
* Support ordinary DictExporter subclasses with additional state and an overridden export method. A shallow per-call copy is permitted; arbitrary custom __copy__ protocols, side effects in user callbacks and concurrent mutation of arbitrary callback state are outside this contract.
* A callback exception must propagate unchanged and leave the supplied exporter's depth/configuration intact. Do not deep-copy a tree or user callbacks and do not temporarily mutate the shared object.

Implement only `library/src/anytree/exporter/jsonexporter.py` and add public tests at `library/tests/test_development_json_exporter.py`. Existing test files and controls are frozen; use the standard library only.
