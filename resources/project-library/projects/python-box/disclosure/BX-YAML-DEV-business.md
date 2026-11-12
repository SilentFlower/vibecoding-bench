# Delivery and verification boundaries

Repair Box.to_yaml for frozen configurations whose lists become tuples containing nested Box objects. Export those nested mappings and sequences as native YAML data through the existing backend, for both strings and files, without unfreezing or mutating the source. Preserve nested values, Unicode, empty sequences, None/bool/numbers, ordinary YAML and JSON behavior, caller serialization options, and meaningful backend errors. YAML sequences may use native lists; do not change to_dict/to_json or global YAML representers, monkeypatch the parser, or weaken frozen mutation guards.

Deliver source changes and public regressions rather than an investigation report alone. Investigate and propose a plan, obtain confirmation, and implement in the same original conversation. Rework actual reported failures. Check original failures, reference passes, and the complete frozen upstream regression separately; reference results do not count as model results.
