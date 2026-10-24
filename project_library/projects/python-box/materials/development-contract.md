# Export frozen nested configuration to YAML without leaking Box objects

Pinned source: https://github.com/cdgriffith/Box @ a4c10e977b574114613431394b30412b50aaacce.

Repair Box.to_yaml for frozen configurations whose lists become tuples containing nested Box objects. Export those nested mappings and sequences as native YAML data through the existing backend, for both strings and files, without unfreezing or mutating the source. Preserve nested values, Unicode, empty sequences, None/bool/numbers, ordinary YAML and JSON behavior, caller serialization options, and meaningful backend errors. YAML sequences may use native lists; do not change to_dict/to_json or global YAML representers, monkeypatch the parser, or weaken frozen mutation guards.

See development-tests.py in this directory for public examples. Deliver original-failing regression tests at the authorized test path without changing existing test controls or dependencies. Document behavior, boundaries, and compatibility policy at the authorized documentation path. Private verification runs independently; public examples do not cover every boundary.
